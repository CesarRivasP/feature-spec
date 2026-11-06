# Master plan

The handler times out after 30000 ms. Retries run inside twelve minutes.
The cache lives 600 seconds; the edge cache warmup runs at boot.
Hits go to the edge cache first. Up to 5 retries, then give up.
Again: 30000 ms, and again 30000 ms.
