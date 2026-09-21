# Clipper clip benchmarks

Download and processing sub-phases are `unavailable` because the existing single-clip helper combines them; wall time is measured around the helper call.

## Videos

| Label | URL | Title | Duration | Captions | Expected |
|---|---|---|---:|---|---|
| short-big-buck-bunny | https://youtu.be/29mtSn1RdMQ?si=OKLlyCHl6u_xKPz7 | Cristiano Ronaldo • Free Clips - 4k 60 fps | 224 | none | skip |
| medium-sintel | https://www.youtube.com/watch?v=eRsGyueVLvQ | Sintel - Open Movie by Blender Foundation | 888 | manual | skip |
| long-placeholder | https://youtu.be/29mtSn1RdMQ?si=OKLlyCHl6u_xKPz7 | Cristiano Ronaldo • Free Clips - 4k 60 fps | 224 | none | skip |
| no-captions-placeholder | https://youtu.be/29mtSn1RdMQ?si=OKLlyCHl6u_xKPz7 | Cristiano Ronaldo • Free Clips - 4k 60 fps | 224 | none | skip |

## Runs

| Label | Mode | Success | Wall (s) | Download (s) | Processing (s) | Size | FPS | Codec | Container | Peak memory | Error |
|---|---|---:|---:|---:|---:|---:|---|---|---|---|---|
| short-big-buck-bunny | fast | yes | 15.844 | unavailable | unavailable | 4525156 | 60.000 | av1 | mov,mp4,m4a,3gp,3g2,mj2 | 9.7 MiB tracemalloc; unavailable |  |
| short-big-buck-bunny | exact | yes | 23.911 | unavailable | unavailable | 13804090 | 60.000 | h264 | mov,mp4,m4a,3gp,3g2,mj2 | 9.2 MiB tracemalloc; unavailable |  |
| medium-sintel | fast | yes | 3.924 | unavailable | unavailable | 4525156 | 60.000 | av1 | mov,mp4,m4a,3gp,3g2,mj2 | 10.0 MiB tracemalloc; unavailable |  |
| medium-sintel | exact | yes | 4.136 | unavailable | unavailable | 13804090 | 60.000 | h264 | mov,mp4,m4a,3gp,3g2,mj2 | 6.7 MiB tracemalloc; unavailable |  |
| long-placeholder | fast | yes | 3.697 | unavailable | unavailable | 4525156 | 60.000 | av1 | mov,mp4,m4a,3gp,3g2,mj2 | 9.4 MiB tracemalloc; unavailable |  |
| long-placeholder | exact | yes | 3.634 | unavailable | unavailable | 13804090 | 60.000 | h264 | mov,mp4,m4a,3gp,3g2,mj2 | 10.0 MiB tracemalloc; unavailable |  |
| no-captions-placeholder | fast | yes | 3.863 | unavailable | unavailable | 4525156 | 60.000 | av1 | mov,mp4,m4a,3gp,3g2,mj2 | 9.2 MiB tracemalloc; unavailable |  |
| no-captions-placeholder | exact | yes | 3.920 | unavailable | unavailable | 13804090 | 60.000 | h264 | mov,mp4,m4a,3gp,3g2,mj2 | 9.1 MiB tracemalloc; unavailable |  |

## Aggregates

- **fast wall time:** min `3.697`, max `15.844`, avg `6.832` seconds
- **exact wall time:** min `3.634`, max `23.911`, avg `8.900` seconds

## Multi-range reuse

- Result: **passed**
- Observed `download_export` calls: `1` (expected one)
- Detail: Existing download_export executed once for two ranges.

Failures are recorded above. Only process URLs for which you have permission.
