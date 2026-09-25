| model                          |       size |     params | backend    | ngl |            test |                  t/s |
| ------------------------------ | ---------: | ---------: | ---------- | --: | --------------: | -------------------: |
| qwen35 27B Q4_K - Medium       |  17.66 GiB |    26.90 B | CUDA       | 999 |          pp2048 |      1293.83 ± 13.43 |
| qwen35 27B Q4_K - Medium       |  17.66 GiB |    26.90 B | CUDA       | 999 |           tg128 |         46.83 ± 0.11 |
| qwen35 27B Q4_K - Medium       |  17.66 GiB |    26.90 B | CUDA       | 999 |  pp2048 @ d8192 |       1241.14 ± 5.55 |
| qwen35 27B Q4_K - Medium       |  17.66 GiB |    26.90 B | CUDA       | 999 |   tg128 @ d8192 |         46.15 ± 0.15 |
| qwen35 27B Q4_K - Medium       |  17.66 GiB |    26.90 B | CUDA       | 999 | pp2048 @ d32768 |       1086.35 ± 4.05 |
| qwen35 27B Q4_K - Medium       |  17.66 GiB |    26.90 B | CUDA       | 999 |  tg128 @ d32768 |         44.19 ± 0.13 |

build: 84e76d8 (1)
