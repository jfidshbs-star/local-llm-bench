| model                          |       size |     params | backend    | ngl |            test |                  t/s |
| ------------------------------ | ---------: | ---------: | ---------- | --: | --------------: | -------------------: |
| seed_oss 36B Q4_K - Medium     |  20.26 GiB |    36.15 B | CUDA       | 999 |          pp2048 |       1080.77 ± 6.99 |
| seed_oss 36B Q4_K - Medium     |  20.26 GiB |    36.15 B | CUDA       | 999 |           tg128 |         39.83 ± 0.03 |
| seed_oss 36B Q4_K - Medium     |  20.26 GiB |    36.15 B | CUDA       | 999 |  pp2048 @ d8192 |        861.53 ± 2.12 |
| seed_oss 36B Q4_K - Medium     |  20.26 GiB |    36.15 B | CUDA       | 999 |   tg128 @ d8192 |         37.32 ± 0.05 |
| seed_oss 36B Q4_K - Medium     |  20.26 GiB |    36.15 B | CUDA       | 999 | pp2048 @ d32768 |        530.57 ± 0.54 |
| seed_oss 36B Q4_K - Medium     |  20.26 GiB |    36.15 B | CUDA       | 999 |  tg128 @ d32768 |         32.54 ± 0.05 |

build: 84e76d8 (1)
