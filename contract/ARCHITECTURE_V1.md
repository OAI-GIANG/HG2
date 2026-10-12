# HG canonical architecture V1

1. Exactly one canonical runtime: the phone runtime (`hg/phone_runtime.py`); it owns state and history.
2. VPS1 runs only `hg/edge.py`: /health, /edge/register, /edge/heartbeat, /edge/status behind `HG_EDGE_TOKEN`.
   It stores device identity + last-seen + seq only, and rejects any payload carrying a model key.
3. VPS2 may mirror the edge for standby/worker/failover; it must never own canonical state.
4. The phone dials outbound over HTTPS; it needs no inbound port and works offline.
5. Two primaries or implicit failover that forks history are prohibited.
