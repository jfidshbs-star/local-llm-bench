| model                          |       size |     params | backend    | ngl |            test |                  t/s |
| ------------------------------ | ---------: | ---------: | ---------- | --: | --------------: | -------------------: |
| gpt-oss 120B MXFP4 MoE         |  59.02 GiB |   116.83 B | CUDA       | 999 |          pp2048 |      1834.81 ± 21.21 |
| gpt-oss 120B MXFP4 MoE         |  59.02 GiB |   116.83 B | CUDA       | 999 |           tg128 |        142.53 ± 0.61 |
| gpt-oss 120B MXFP4 MoE         |  59.02 GiB |   116.83 B | CUDA       | 999 |  pp2048 @ d8192 |       1767.23 ± 2.04 |
| gpt-oss 120B MXFP4 MoE         |  59.02 GiB |   116.83 B | CUDA       | 999 |   tg128 @ d8192 |        136.51 ± 0.69 |
| gpt-oss 120B MXFP4 MoE         |  59.02 GiB |   116.83 B | CUDA       | 999 | pp2048 @ d32768 |       1609.10 ± 7.50 |
| gpt-oss 120B MXFP4 MoE         |  59.02 GiB |   116.83 B | CUDA       | 999 |  tg128 @ d32768 |        125.84 ± 0.65 |

build: 84e76d8 (1)
