#!/usr/bin/env bash
# Сценарий арендованной видеокарты (A100 80 ГБ или 2× RTX 4090 48 ГБ, Ubuntu + драйвер NVIDIA). Один запуск — все замеры.
# Несколько карт llama.cpp делит сам (слоями), флаги те же.
# Порядок: llama.cpp (сборка с CUDA) → модели → для каждой: 3 прогона извлечения, инъекции,
# скорость по длине контекста (llama-bench). Итог — results-gpu.tar.gz, забираем scp и гасим машину.
#
# Запуск на машине:  bash gpu_run.sh 2>&1 | tee -a gpu_run.log
# Возобновляемый: если сервер остановился (кончилась предоплата), после запуска — та же команда.
# Сборка, скачанные модели и законченные замеры (отметки results/done-*) повторно не делаются.
# Каталог стенда с корпусом копируется заранее:  scp -r <каталог стенда> root@<ip>:/root/bench
set -euo pipefail
cd "$(dirname "$0")"
M=/root/models; mkdir -p "$M" results
nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv | tee results/gpu-info.csv
nproc | tee results/cpu-count.txt
# Сколько видеопамяти (ГБ, сумма по картам). От этого зависит раскладка модели:
# влезает целиком — всё на карту; не влезает — эксперты MoE (gpt-oss) или часть слоёв (Qwen) в обычную память.
VRAM=$(nvidia-smi --query-gpu=memory.total --format=csv,noheader,nounits | awk '{s+=$1} END {print int(s/1024)}')
echo "видеопамять: ${VRAM} ГБ" | tee results/vram-total.txt

# --- 1. llama.cpp: сборка из исходников с CUDA (docker с nvidia-toolkit есть не у всех провайдеров) ----
if [ ! -x /root/llama.cpp/build/bin/llama-server ]; then
  apt-get update -qq && apt-get install -y -qq git cmake build-essential libcurl4-openssl-dev python3-venv >/dev/null
  git clone -q --depth 1 https://github.com/ggml-org/llama.cpp /root/llama.cpp
  export PATH=/usr/local/cuda/bin:$PATH
  command -v nvcc >/dev/null || { echo "нет nvcc — ставлю CUDA toolkit"; apt-get install -y -qq nvidia-cuda-toolkit >/dev/null; }
  nvcc --version | tail -1
  # сборка только под видеокарту этой машины (A100 = sm_80, RTX 4090 = sm_89) — в разы быстрее, чем под все
  cmake -S /root/llama.cpp -B /root/llama.cpp/build -DGGML_CUDA=ON -DCMAKE_CUDA_ARCHITECTURES=native \
        -DCMAKE_BUILD_TYPE=Release >/dev/null
  cmake --build /root/llama.cpp/build -j"$(nproc)" --target llama-server llama-bench >/dev/null
fi
LC=/root/llama.cpp/build/bin
(cd /root/llama.cpp && git log -1 --format='%h %cd' --date=short) | tee results/llama-cpp-version.txt

# --- 2. Python для стенда --------------------------------------------------------------------------------
[ -x /root/venv/bin/hf ] || { python3 -m venv /root/venv && /root/venv/bin/pip install -q openai lxml "huggingface_hub[hf_transfer]"; }
PY=/root/venv/bin/python
export HF_HUB_ENABLE_HF_TRANSFER=1

# --- 3. Модели (параллельно с первым замером качать нельзя — диск и сеть; качаем сразу все) --------------
dl() { /root/venv/bin/hf download "$1" "$2" --local-dir "$M" >/dev/null && ls -l "$M/$2"; }  # докачивает, готовое пропускает
time dl ggml-org/gpt-oss-120b-GGUF gpt-oss-120b-MXFP4.gguf
time dl ggml-org/Qwen3.8-27B-GGUF Qwen3.8-27B-Q4_K_M.gguf
[ "$VRAM" -ge 75 ] && time dl ggml-org/Qwen3.8-27B-GGUF Qwen3.8-27B-Q8_0.gguf
time dl NousResearch/Hermes-4.3-36B-GGUF hermes-4_3_36b-Q4_K_M.gguf   # назван в вакансии; 21,8 ГБ, Apache 2.0

serve() {  # $1 файл модели, $2 доп. флаги
  $LC/llama-server -m "$M/$1" -ngl 999 -c "${CTX:-65536}" --jinja --host 127.0.0.1 --port 8080 -np 1 $2 \
    > "results/server-$1.log" 2>&1 &
  SRV=$!
  until curl -s 127.0.0.1:8080/health | grep -q ok; do
    kill -0 $SRV 2>/dev/null || { echo "llama-server упал:"; tail -20 "results/server-$1.log"; exit 1; }
    sleep 2
  done
  nvidia-smi --query-gpu=memory.used --format=csv,noheader | tee "results/vram-$1.txt"
}
stop() { kill $SRV; wait $SRV 2>/dev/null || true; }

run_model() {  # $1 файл, $2 тег, $3 reasoning ('' для Qwen — выключаем через шаблон), $4 флаги сервера, $5 bench|nobench
  if [ -e "results/done-$2" ]; then echo "== $2 уже замерен, пропуск"; return; fi
  serve "$1" "${4:-}"
  $PY extract_bench.py --base-url http://127.0.0.1:8080/v1 --model local --tag "a100-$2" --runs 3 --reasoning "$3" \
    | tail -3
  $PY injection_bench.py --base-url http://127.0.0.1:8080/v1 --model local --tag "a100-$2" --reasoning "$3" | tail -2
  stop
  # скорость по длине контекста: чтение 2048 токенов и ответ 128 на глубине 0 / 8k / 32k
  # bench — только когда модель целиком на карте; с --cpu-moe скорость берём из timings сервера в results
  if [ "${5:-bench}" = "bench" ]; then
    $LC/llama-bench -m "$M/$1" -ngl 999 -p 2048 -n 128 -d 0,8192,32768 -r 3 -o md | tee "results/bench-$2.md" || true
  fi
  touch "results/done-$2"
}

if [ "$VRAM" -ge 75 ]; then   # A100/H100 80 ГБ, 2× 48 ГБ: всё на карте, три модели
  CTX=65536
  run_model gpt-oss-120b-MXFP4.gguf gptoss120b low "" bench
  run_model Qwen3.8-27B-Q4_K_M.gguf qwen27b-q4 "" "--reasoning-budget 0" bench
  run_model Qwen3.8-27B-Q8_0.gguf qwen27b-q8 "" "--reasoning-budget 0" bench
  run_model hermes-4_3_36b-Q4_K_M.gguf hermes43-36b-q4 "" "--reasoning-budget 0" bench
else                          # 24–48 ГБ: gpt-oss — эксперты MoE в обычную память (--cpu-moe), Qwen Q4 — целиком на карте,
  CTX=24576                   # Q8 (28,6 ГБ) пропускаем. Контекст: самая длинная страница ≈16,8 тыс. токенов + ответ
  run_model gpt-oss-120b-MXFP4.gguf gptoss120b-cpumoe low "--cpu-moe" nobench
  run_model Qwen3.8-27B-Q4_K_M.gguf qwen27b-q4 "" "--reasoning-budget 0" bench
  run_model hermes-4_3_36b-Q4_K_M.gguf hermes43-36b-q4 "" "--reasoning-budget 0" bench
fi
echo "видеопамять ${VRAM} ГБ, контекст $CTX" | tee results/layout.txt

tar czf results-gpu.tar.gz results
echo "ГОТОВО: $(pwd)/results-gpu.tar.gz — забрать scp и остановить машину"
