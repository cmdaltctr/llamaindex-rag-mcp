# Diagnosing `ECONNREFUSED` in Node.js network clients

The Node.js error code `ECONNREFUSED` is returned when a TCP connection
attempt is actively rejected by the target host. The kernel received a TCP
RST in response to the SYN packet, which means there is a working network
path but **nothing is listening** on the requested port. `ECONNREFUSED` is
distinct from `ETIMEDOUT` (no response at all) and `EHOSTUNREACH` (no
route to the host).

## When you see `ECONNREFUSED`

The most common producers of `ECONNREFUSED` in a Node.js application:

- The target service has not finished starting up. A common race in
  docker-compose stacks: the API container connects to the database before
  Postgres has bound to its port. The API logs `ECONNREFUSED` and exits.
- The target service crashed. If your `pm2 list` shows a service in `errored`
  state, expect `ECONNREFUSED` from anything that talks to it.
- The target service is bound to the wrong interface. A service that listens
  on `127.0.0.1:5432` will reject connections from `172.18.0.2`, returning
  `ECONNREFUSED` from outside the container.
- A firewall is sending RSTs on the listener's behalf. Less common today, but
  some corporate networks still do this.

## Distinguishing `ECONNREFUSED` from neighbours

| Error code        | Cause                                                  |
| ----------------- | ------------------------------------------------------ |
| `ECONNREFUSED`    | Connection actively refused (RST received)             |
| `ETIMEDOUT`       | Connection attempt timed out (no response)             |
| `EHOSTUNREACH`    | No route to host (network layer)                       |
| `ENOTFOUND`       | DNS resolution failed                                  |
| `EADDRINUSE`      | Local port already in use (server-side, not client)    |

## A retry policy that works

`ECONNREFUSED` is one of the few error codes where exponential backoff with
jitter is almost always the right answer, because it usually means "the
target is not yet ready" rather than "the target is broken". A reasonable
default for a service-mesh client:

```
initial: 100 ms
factor:  2.0
max:     8 s
jitter:  ±25 %
attempts: 6
```

If you exhaust the attempts and still see `ECONNREFUSED`, the target is
down, not slow. Page the on-call.
