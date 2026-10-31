# Bot state — don't edit by hand

- `state.json`: what was posted where and when (with links), the queue's assigned slots, and retry counters.
- `tokens.enc`: tokens the bot renews itself (Threads, Pinterest), encrypted with the `TOKEN_STORE_KEY` secret.

The publish workflow updates and commits these files. To re-post something, delete that
post's entry from `state.json`.
