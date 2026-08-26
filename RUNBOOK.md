# Runbook — do these in order

Everything here assumes you're on the venue wifi. The model endpoints are not
reachable from outside.

---

## 1. Can you reach the models? (2 minutes)

```bash
curl -m 6 http://129.212.182.232:8001/v1/models
```

- **Something comes back** → good, go to step 2.
- **Nothing / hangs** → you're not on the right network, or that box is down.
  Try the other three endpoints in `.env.example`. If all four are silent, ask
  in `#hackathon_cambridge_2026` — don't spend twenty minutes debugging your
  own machine for someone else's server.

## 2. Start the runtime on your laptop (5 minutes)

Qwen needs no API key, which is one less thing to get wrong.

```bash
export FLWR_MODEL_API_ENDPOINT='http://129.212.182.232:8001/v1/responses'
unset FLWR_MODEL_API_KEY
uv run flower-superlink --insecure
```

Leave that terminal open. It stays running.

Add this once to `~/.flwr/config.toml`:

```toml
[superlink.local-agent]
address = "127.0.0.1:9093"
insecure = true
```

## 3. First real run (5 minutes)

New terminal:

```bash
uv run flwr run . local-agent \
  --run-config 'model.id="/models/Qwen3.5-397B-A17B-FP8"' --stream
```

**What you should see:** the site table, the counts, then
`BLOCKED - AWAITING SPONSOR SIGN-OFF` with a token, then the AI explaining in
words that it's blocked.

**Time it.** Write the number of seconds on the whiteboard. Everything else
today is budgeted against it — there's a five-minute cap per run.

### If it fails

- **Model returned nothing parseable** → the router got confused. Try
  `model.id="glm-5.2-fp8"` with that endpoint + its key from Slack.
- **Times out** → run with `--run-config 'policy.narrate=false'`. That skips
  the AI entirely and finishes in two seconds. Your demo still works.

## 4. Release the result

Copy the token it printed:

```bash
uv run flwr run . local-agent \
  --run-config 'model.id="/models/Qwen3.5-397B-A17B-FP8" policy.approval-token="c0ebf445"' \
  --stream
```

Now it writes the actual feasibility answer. **Check it says "2 of 3 sites"** —
if it reports the total as the whole network, the prompt needs tightening and
that's a real finding, not a bug to hide.

## 5. Publish to Flower Hub — REQUIRED

You cannot submit without this. **Ask a mentor the exact command** — it isn't in
the docs we read. Do it by 15:30, not 17:00.

## 6. Record the demo

Screen-record the whole thing once it works. By 16:30. Once that file exists you
cannot lose the demo, whatever happens to the network.

---

## The panic button

If anything is on fire:

```bash
uv run python -m trialgrid.demo
```

No network, no AI, no Flower. Runs in 3 milliseconds. Shows the sites, the
counts, the suppressed cells, the abstaining site, and the block. That's the
whole safety story — it just doesn't talk.

---

## The one-liner if a judge asks what it does

> Three hospitals answer whether a trial can recruit. No patient record leaves
> any of them — only counts cross the wire. One hospital declines, and we report
> "two of three", never zero, because a site that abstains isn't an absence of
> patients. A human signs off before any number is released.

## If a judge asks what stops the AI misbehaving

> Nothing the AI is told. The hospital agents don't call an AI at all, so
> there's nothing to trick. The AI only routes the question at the start and
> writes the summary at the end, and in between it's ordinary code deciding.
> If you deleted every instruction we give it, no patient record would still
> get out.
