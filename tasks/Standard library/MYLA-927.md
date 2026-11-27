---
id: MYLA-927
title: "std.http: past the room for parked responses, workers sending themselves can starve the parked ones"
type: bug
status: backlog
priority: low
labels: [std, http]
---
Found by [[MYLA-833]]. A response its socket doesn't take at once waits parked, its bytes within `workers` × `max_body_bytes` (`send_room`); past that room the worker sends the response itself, as every response was sent before, waiting with `write_ms` for each 64 KiB. A parked response needs a worker to go on with it once its socket takes more. When every worker is sending a response past the room to a client that reads another connection's parked response first, the parked one has no worker: the held workers time out (`TimedOut`, the connections cut) before the client reads their responses.

Reproduction: a server with 2 workers and `max_body_bytes` 4,000,000 (a room of 8 MB); four connections whose requests each ask for a 4 MB response (test_http's `/echo` of a 4 MB body) on loopback under load (four busy processes beside it, so that no response goes out at once); the client reads the connections in order. The first two are parked, the other two held by the workers, and if the client reads a parked one first, the held ones are cut after `write_ms`. With a room of `workers` responses `test_a_body_dribbled_costs_its_pieces_not_its_size` failed so 5 of 5 under that load (MYLA-833's evidence).

- [ ] A worker past the room doesn't hold itself against a parked response: for example it parks its response too and waits for room on a notifier instead of the socket, or the room grows while every worker sends
- [ ] A test with the reproduction above, and its rate before and after
