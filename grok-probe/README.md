# Grok Memorization Probe

Interactive tooling to inspect whether Grok-family language models regurgitate archived tweets when prompted with partial text. The project bundles a small Express proxy for OpenRouter alongside a browser UI that fetches tweets from Supabase and compares model continuations against the ground truth.

## Prerequisites
- Node.js 18+
- An OpenRouter API key with access to the Grok models referenced in `config.json`
- (Optional) A Supabase project that mirrors the expected tables (`tweets`, `account`, `profile`) and anon key

Install dependencies once:

```bash
npm install
```

## Configuration
- Provide environment variables via your shell or a `.env` file (loaded automatically through `dotenv`):
  - `OPENROUTER_API_KEY` (or `OPENROUTER_KEY`) – required to call OpenRouter
  - `OR_HTTP_REFERER`, `OR_X_TITLE` – optional metadata headers forwarded to OpenRouter
- Adjust `config.json` to tailor the probe. You can change:
  - `models`: list of OpenRouter model identifiers to compare
  - `defaults`: decoding parameters (prefix length, temperature, logprobs, etc.) applied unless the UI overrides them
  - `prompts.system` / `prompts.user`: templates the server injects when constructing the chat completion call

If `config.json` is removed or malformed the server falls back to built-in defaults (`server.js:31-45`).

## Running the server
Launch the Express server, which also serves the static frontend:

```bash
OPENROUTER_API_KEY=sk-or-... npm start
```

The app listens on `http://localhost:5173` by default. Navigate there to open the UI.

## Using the UI
1. **Fetch tweet** – Click *Fetch Random Tweet*. The frontend loads a random entry via `web/fetchTweet.js`. If that helper is absent or fails, the app prompts you to paste text manually.
2. **Tune parameters** – Tick model checkboxes and adjust decoding knobs (prefix length, `top_k`, penalties, stop tokens, etc.). Presets in the dropdown quickly swap common configurations.
3. **Run probe** – Press *Run Probe*. The frontend posts your selections to `/api/probe`; the server queries OpenRouter for each model in parallel.
4. **Inspect results** – Each card shows the model continuation, warning flags (e.g., stripped parameters), boolean exact-match checks, character-level similarity, and optional token logprobs.
5. **Review history** – The last 10 probes persist in `localStorage`. Use *View* to reload a run or *Re-run* to replay it with the captured parameters.

Highlights:
- Tweet rendering splits prefix vs. suffix so you can see exactly what the model was given.
- The UI computes Levenshtein similarity and exact continuation checks to flag likely memorization events.
- Token logprob dumps (when requested) surface distributional context for each generated token.

## Architecture
```
project-root
├── server.js        # Express server, OpenRouter proxy, static hosting
├── config.json      # Model roster, default decoding params, prompt templates
├── web/
│   ├── index.html   # UI shell and control layout
│   ├── app.js       # Frontend logic: fetching tweets, running probes, rendering results/history
│   ├── styles.css   # Dark theme styling for controls and result cards
│   └── fetchTweet.js# Supabase-powered random tweet helper (auto-imported by app.js)
└── fetchTweet.js    # Legacy DOM helper to render a specific tweet ID
```

`server.js` consolidates request payloads with config defaults, builds a chat prompt, and retries OpenRouter calls without unsupported parameters when providers reject them. Responses are streamed back to the browser alongside the gold tweet text so the UI can compute metrics client-side.

## Development notes
- The repository currently tracks local modifications (run `git status` to inspect). Commit intentionally when ready.
- Supabase anon key embedded in the frontend is treated as public; rotate it if you intend to expose the app.
- The sandbox prohibits outbound network calls unless the environment grants access; ensure your local setup can reach OpenRouter and Supabase.

## Troubleshooting
- **"OPENROUTER_API_KEY not set on server"** – export the variable before starting or place it in `.env`.
- **"Prefix too long for this tweet"** – the UI requested more prefix characters than the tweet contains; lower `prefix_len`.
- **Model errors with "Argument not supported"** – the backend automatically strips unsupported parameters and records the action under the card’s warnings section.

## License
No license file is provided. Add one before distributing or open-sourcing the project.
