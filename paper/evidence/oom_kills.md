# Kernel out-of-memory kills during the blind campaign and its re-runs

Source: `dmesg` of the measurement VM, where every process shares one memory cgroup of about
15 GiB, read on 2026-10-27 at 21:55 UTC. The ring buffer had already dropped its older lines:
the two kills of 16:34 UTC come from a read of the same log at 21:35 UTC (raw lines not kept),
and kills before 16:34 UTC are not available. Attribution: a per-second sampler logged pid,
RSS and cell of every benchmark worker from 15:48 UTC; a kill is attributed to the worker whose
last sample lies within 4 s of it, preferring the closest RSS (kernel pids are host pids and
differ from the sampled ones).

Harness: *campaign* = the blind run (`2346982`, two workers sharing the cgroup);
*supplementary* = the corrected-harness fused run (`33515a3`, return codes recorded);
*isolated re-run* = the cells killed in the campaign, re-run one at a time at `9b62a75`
(benchmark code identical to `2346982`) with no other benchmark running.

| kill (UTC) | killed anon-RSS | cell (circuit workload mode) | sampled max RSS | run |
|---|---:|---|---:|---|
| 16:34:24 | 7.8 GiB | cadder_30 nonequiv sparse/algebra | 6.7 GiB | campaign |
| 16:34:39 | 13.0 GiB | adder_24 equiv zdd-native/loop-sorted | 12.9 GiB | campaign |
| 16:56:18 | 10.1 GiB | adder_31 simulate zdd-native/loop-sorted | 10.1 GiB | campaign |
| 16:57:51 | 12.8 GiB | cadder_30 simulate sparse/algebra | 12.5 GiB | campaign |
| 17:06:09 | 13.9 GiB | adder_31 nonequiv sparse/algebra | 12.5 GiB | campaign |
| 17:19:43 | 9.1 GiB | adder_31 simulate zdd-native/algebra | 9.8 GiB | campaign |
| 17:49:01 | 10.2 GiB | adder_24 equiv sparse/algebra | 10.1 GiB | campaign |
| 17:49:27 | 8.9 GiB | adder_31 equiv sparse/algebra | 8.3 GiB | campaign |
| 18:17:46 | 7.1 GiB | rand_16_400_2 simulate zdd-native/fused | 6.4 GiB | supplementary |
| 18:19:24 | 6.9 GiB | rand_32_400_2 simulate zdd-native/fused | 8.5 GiB | supplementary |
| 18:21:20 | 8.6 GiB | not sampled; the only cell of that run recorded as killed (return code −9) then is rand_64_400_2 simulate zdd-native/fused | — | supplementary |
| 18:25:23 | 9.0 GiB | adder_31 simulate zdd-native/fused (recorded with return code −9) | 10.0 GiB | supplementary |
| 21:41:45 | 14.4 GiB | adder_24 equiv zdd-native/loop-sorted | 13.2 GiB | isolated re-run |
| 21:48:22 | 14.4 GiB | cadder_30 simulate sparse/algebra | 14.1 GiB | isolated re-run |
| 21:48:57 | 14.4 GiB | adder_31 simulate sparse/algebra | 13.6 GiB | isolated re-run |
| 21:51:26 | 14.4 GiB | cadder_30 nonequiv sparse/algebra | 13.4 GiB | isolated re-run |
| 21:51:57 | 14.4 GiB | adder_31 nonequiv sparse/algebra | 13.2 GiB | isolated re-run |
| 21:52:48 | 14.4 GiB | adder_24 equiv sparse/algebra | 14.0 GiB | isolated re-run |
| 21:53:21 | 14.4 GiB | adder_31 equiv sparse/algebra | 13.2 GiB | isolated re-run |

Raw kernel lines still in the buffer:

```
[17976.679643] Memory cgroup out of memory: Killed process 94727 (python) total-vm:11913404kB, anon-rss:10548780kB, file-rss:5680kB, shmem-rss:0kB, UID:1000 pgtables:20884kB oom_score_adj:0
[18069.580057] Memory cgroup out of memory: Killed process 96588 (python) total-vm:14148804kB, anon-rss:13464948kB, file-rss:5704kB, shmem-rss:0kB, UID:1000 pgtables:26744kB oom_score_adj:0
[18567.994667] Memory cgroup out of memory: Killed process 102196 (python) total-vm:17705156kB, anon-rss:14604852kB, file-rss:5848kB, shmem-rss:0kB, UID:1000 pgtables:28952kB oom_score_adj:0
[19381.446657] Memory cgroup out of memory: Killed process 110216 (python) total-vm:14009532kB, anon-rss:9551500kB, file-rss:5720kB, shmem-rss:0kB, UID:1000 pgtables:18932kB oom_score_adj:0
[21139.679195] Memory cgroup out of memory: Killed process 132038 (python) total-vm:11088248kB, anon-rss:10668224kB, file-rss:5636kB, shmem-rss:0kB, UID:1000 pgtables:21204kB oom_score_adj:0
[21165.668951] Memory cgroup out of memory: Killed process 132586 (python) total-vm:9656528kB, anon-rss:9282712kB, file-rss:5692kB, shmem-rss:0kB, UID:1000 pgtables:18500kB oom_score_adj:0
[22864.666248] Memory cgroup out of memory: Killed process 153625 (python) total-vm:7981312kB, anon-rss:7491432kB, file-rss:5572kB, shmem-rss:0kB, UID:1000 pgtables:14904kB oom_score_adj:0
[22962.657106] Memory cgroup out of memory: Killed process 154363 (python) total-vm:9291012kB, anon-rss:7227320kB, file-rss:5600kB, shmem-rss:0kB, UID:1000 pgtables:14368kB oom_score_adj:0
[23078.193289] Memory cgroup out of memory: Killed process 155431 (python) total-vm:10339596kB, anon-rss:8975812kB, file-rss:5392kB, shmem-rss:0kB, UID:1000 pgtables:17804kB oom_score_adj:0
[23321.389851] Memory cgroup out of memory: Killed process 158131 (python) total-vm:9816320kB, anon-rss:9468100kB, file-rss:5560kB, shmem-rss:0kB, UID:1000 pgtables:18760kB oom_score_adj:0
[35103.325461] Memory cgroup out of memory: Killed process 233019 (python) total-vm:15582404kB, anon-rss:15097300kB, file-rss:5496kB, shmem-rss:0kB, UID:1000 pgtables:29788kB oom_score_adj:0
[35500.918633] Memory cgroup out of memory: Killed process 237021 (python) total-vm:16042180kB, anon-rss:15098672kB, file-rss:5432kB, shmem-rss:0kB, UID:1000 pgtables:29940kB oom_score_adj:0
[35535.587364] Memory cgroup out of memory: Killed process 237339 (python) total-vm:17705156kB, anon-rss:15094560kB, file-rss:5460kB, shmem-rss:0kB, UID:1000 pgtables:29912kB oom_score_adj:0
[35684.644183] Memory cgroup out of memory: Killed process 238641 (python) total-vm:16068804kB, anon-rss:15099332kB, file-rss:5436kB, shmem-rss:0kB, UID:1000 pgtables:29996kB oom_score_adj:0
[35715.034313] Memory cgroup out of memory: Killed process 238907 (python) total-vm:17710276kB, anon-rss:15094452kB, file-rss:5488kB, shmem-rss:0kB, UID:1000 pgtables:29924kB oom_score_adj:0
[35766.903763] Memory cgroup out of memory: Killed process 239204 (python) total-vm:17518856kB, anon-rss:15094456kB, file-rss:5476kB, shmem-rss:0kB, UID:1000 pgtables:29928kB oom_score_adj:0
[35799.706457] Memory cgroup out of memory: Killed process 239613 (python) total-vm:17710276kB, anon-rss:15094520kB, file-rss:5388kB, shmem-rss:0kB, UID:1000 pgtables:29916kB oom_score_adj:0
```
