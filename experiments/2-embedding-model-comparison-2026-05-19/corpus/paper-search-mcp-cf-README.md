# paper-search-mcp-cf

A **remote MCP server** for academic paper search, deployed on Cloudflare Workers. Also works locally via stdio.

Ported from [openags/paper-search-mcp](https://github.com/openags/paper-search-mcp).

Searches **8 academic sources** concurrently and returns standardized paper metadata. PDF URLs are returned in results — your agent can fetch them using its own tools (fetch, firecrawl, browser, etc.).

## Tools

### Per-Source Search (8 tools)

| Tool                    | Source               | API Type | API Key Required?              |
| ----------------------- | -------------------- | -------- | ------------------------------ |
| `search_arxiv`            | arXiv                  | Atom XML | No                             |
| `search_semantic`         | Semantic Scholar      | JSON     | Optional (better rate limits)  |
| `search_pubmed`           | PubMed                | JSON     | No                             |
| `search_crossref`         | CrossRef              | JSON     | No                             |
| `search_biorxiv`          | bioRxiv               | JSON     | No                             |
| `search_medrxiv`          | medRxiv               | JSON     | No                             |
| `search_openalex`         | OpenAlex              | JSON     | No                             |
| `search_google_scholar`   | Google Scholar        | HTML     | No (may be blocked from cloud) |

### Utility Tools (2 tools)

| Tool                      | Description                        |
| ------------------------- | ---------------------------------- |
| `get_crossref_paper_by_doi` | Lookup a paper by DOI via CrossRef |
| `get_semantic_paper_by_id`  | Lookup a paper by ID via Semantic Scholar |

### Unified Search (1 tool)

| Tool           | Description                                                              |
| -------------- | ------------------------------------------------------------------------ |
| `search_papers` | Fans out to all selected sources, merges and deduplicates results       |

### Prompts (2 prompts)

| Prompt             | Description                                                |
| ------------------ | ---------------------------------------------------------- |
| `literature-review`  | Search multiple sources and generate a research summary    |
| `paper-lookup`       | Find a specific paper by DOI or title across all sources   |

---

## 🚀 Running on Cloudflare (Remote)

### Authentication

#### Layer 1 — Bearer Token (Server Gate)

Set these as Cloudflare Worker secrets:

```bash
wrangler secret put OWNER_API_KEY   # Your personal token
wrangler secret put TEAM_API_KEY    # Shared token for colleagues
```

Generate keys with `openssl rand -base64 32`.

#### Layer 2 — Per-User API Key (Optional)

The `X-Semantic-Scholar-Api-Key` header is **optional**. Semantic Scholar works without a key but with lower rate limits (100 req/5min vs 1000 req/5min with a key).

### Client Configuration

**You (owner):**
```json
{
  "paper-search": {
    "command": "npx",
    "args": [
      "mcp-remote",
      "https://paper-search-mcp-cf.<your-account>.workers.dev/mcp",
      "--header",
      "Authorization:Bearer <YOUR_OWNER_API_KEY>",
      "--header",
      "X-Semantic-Scholar-Api-Key:<your-semantic-key>"
    ]
  }
}
```

**Colleagues (team):**
```json
{
  "paper-search": {
    "command": "npx",
    "args": [
      "mcp-remote",
      "https://paper-search-mcp-cf.<your-account>.workers.dev/mcp",
      "--header",
      "Authorization:Bearer <SHARED_TEAM_API_KEY>",
      "--header",
      "X-Semantic-Scholar-Api-Key:<their-own-semantic-key>"
    ]
  }
}
```

### Deploy

```bash
# 1. Set secrets
wrangler secret put OWNER_API_KEY
wrangler secret put TEAM_API_KEY

# (Optional) Set Google Scholar proxy
wrangler secret put GOOGLE_SCHOLAR_PROXY_URL

# 2. Deploy
npm run deploy
```

---

## 💻 Running Locally (Stdio)

No Cloudflare account needed. Runs on any machine with Node.js.

```bash
# 1. Clone
git clone https://github.com/cmdaltctr/paper-search-mcp-cf.git
cd paper-search-mcp-cf

# 2. Install
npm install

# 3. Run (optionally with Semantic Scholar key)
SEMANTIC_SCHOLAR_API_KEY=your-key npm run local
```

### MCP Client Configuration

After cloning, configure your MCP client using the **absolute path** to the repo (replace `/path/to/paper-search-mcp-cf` below):

#### Claude Desktop

Edit `~/Library/Application Support/Claude/claude_desktop_config.json` (macOS) or `%APPDATA%\Claude\claude_desktop_config.json` (Windows):

```json
{
  "mcpServers": {
    "paper-search": {
      "command": "npx",
      "args": ["tsx", "/path/to/paper-search-mcp-cf/src/local.ts"],
      "env": {
        "SEMANTIC_SCHOLAR_API_KEY": "your-key-here"
      }
    }
  }
}
```

#### Claude Code (CLI)

Add to your project or global config:

```bash
# Project-level
claude mcp add paper-search -- npx tsx /path/to/paper-search-mcp-cf/src/local.ts
claude mcp set paper-search --env SEMANTIC_SCHOLAR_API_KEY=your-key-here

# Or global (user-level)
claude mcp add --scope user paper-search -- npx tsx /path/to/paper-search-mcp-cf/src/local.ts
claude mcp set --scope user paper-search --env SEMANTIC_SCHOLAR_API_KEY=your-key-here
```

Or add directly to `.claude/settings.json` or `~/.claude/settings.json`:

```json
{
  "mcpServers": {
    "paper-search": {
      "command": "npx",
      "args": ["tsx", "/path/to/paper-search-mcp-cf/src/local.ts"],
      "env": {
        "SEMANTIC_SCHOLAR_API_KEY": "your-key-here"
      }
    }
  }
}
```

#### OpenCode

Add to `~/.config/opencode/opencode.json` or project-level `opencode.json`:

```json
{
  "mcp": {
    "paper-search": {
      "type": "stdio",
      "command": "npx",
      "args": ["tsx", "/path/to/paper-search-mcp-cf/src/local.ts"],
      "env": {
        "SEMANTIC_SCHOLAR_API_KEY": "your-key-here"
      }
    }
  }
}
```

#### Cursor / Other MCP Clients

Use the same stdio pattern:

```json
{
  "paper-search": {
    "command": "npx",
    "args": ["tsx", "/path/to/paper-search-mcp-cf/src/local.ts"],
    "env": {
      "SEMANTIC_SCHOLAR_API_KEY": "your-key-here"
    }
  }
}
```

---

## For Your AI - One-Click Setup Prompt

Copy the entire block below and paste it to your AI coding agent (Claude, OpenCode, Cursor, etc.). The AI will handle everything automatically.

> **Instructions**: Replace `<path-to-project>` with the folder where you want it installed (e.g., `~/projects` or `C:\Users\You\projects`).

---

```
You are installing the paper-search-mcp-cf project. This is an MCP server that searches academic papers from 8 sources (arXiv, PubMed, CrossRef, Semantic Scholar, OpenAlex, bioRxiv, medRxiv, Google Scholar).

INSTALLATION DIRECTORY: <path-to-project>/paper-search-mcp-cf

STEPS:
1. Clone the repo: git clone https://github.com/cmdaltctr/paper-search-mcp-cf.git <path-to-project>/paper-search-mcp-cf
2. cd into the directory
3. Run: npm install
4. Run: npx tsc --noEmit  (verify type check passes)
5. Create a test file or run: SEMANTIC_SCHOLAR_API_KEY=demo npm run local
   (kill it after 3 seconds to confirm it starts)

After installation, configure the MCP client. Use the ABSOLUTE path to src/local.ts:

For Claude Desktop (edit claude_desktop_config.json):
{
  "mcpServers": {
    "paper-search": {
      "command": "npx",
      "args": ["tsx", "ABSOLUTE_PATH/src/local.ts"],
      "env": { "SEMANTIC_SCHOLAR_API_KEY": "<optional-api-key>" }
    }
  }
}

For Claude Code (run in terminal):
claude mcp add paper-search -- npx tsx ABSOLUTE_PATH/src/local.ts
claude mcp set paper-search --env SEMANTIC_SCHOLAR_API_KEY=<optional-api-key>

For OpenCode (edit opencode.json):
{
  "mcp": {
    "paper-search": {
      "type": "stdio",
      "command": "npx",
      "args": ["tsx", "ABSOLUTE_PATH/src/local.ts"],
      "env": { "SEMANTIC_SCHOLAR_API_KEY": "<optional-api-key>" }
    }
  }
}

To test it works, ask the user to try: "search for papers about AI hallucination using the search_papers tool"

NOTES:
- No Cloudflare account needed for local setup
- Semantic Scholar API key is optional (provides better rate limits)
- All 11 tools + 2 prompts will be available after restarting the MCP client
- PDF URLs are returned in results — the AI agent can fetch them with its own tools
```

---

## Development

```bash
# Install dependencies
npm install

# Start local stdio server (standalone, no Cloudflare)
SEMANTIC_SCHOLAR_API_KEY=your-key npm run local

# Start Cloudflare dev server (requires .env with OWNER_API_KEY and TEAM_API_KEY)
npm run dev

# Deploy to Cloudflare
npm run deploy

# Type check
npm run type-check

# Test with MCP Inspector
npx @modelcontextprotocol/inspector
```

## Architecture

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│  MCP Client     │────▶│  Cloudflare      │────▶│  Academic APIs  │
│  (Claude, etc.) │     │  Worker          │     │  (arXiv, PubMed,│
│  Bearer + Key   │     │  createMcpHandler │     │   CrossRef, etc)│
└─────────────────┘     └──────────────────┘     └─────────────────┘
                              │
                         ┌────┴────┐
                         │  Auth   │
                         │ Bearer  │
                         │ Check   │
                         └─────────┘

Or locally via stdio:

┌─────────────────┐     ┌──────────────────┐
│  MCP Client     │────▶│  StdioServer      │
│  (stdio config) │     │  Transport       │
│                 │     │  src/local.ts    │
└─────────────────┘     └──────────────────┘
```

## Notes

### Google Scholar Limitations
Google Scholar actively blocks automated access, especially from cloud/data-center IPs. The MCP gracefully degrades: if Google Scholar fails (blocked, CAPTCHA), the error is isolated — all other sources still work. For better reliability, you can set a proxy via the `GOOGLE_SCHOLAR_PROXY_URL` secret.

### PDF Access
Search results include `pdf_url` and `url` fields. The MCP does NOT download or read PDFs — it returns the URLs so your agent can fetch them using its own tools (fetch, firecrawl MCP, browser, etc.).

### IACR ePrint Archive
Not included in v1. The IACR search tool (for cryptography papers) can be added in a future update.

### bioRxiv / medRxiv
These APIs filter by category within a 30-day window and may return empty results depending on the query. Try category names like `bioinformatics`, `neuroscience`, `infectious_diseases`, `oncology`.

### Semantic Scholar Cloudflare Block
Semantic Scholar's API blocks Cloudflare egress IPs. The remote Cloudflare Worker version cannot access Semantic Scholar, but the local stdio version works fine. Use the local version if you need Semantic Scholar results.

## Sources Not Ported

The paper-search-mcp supports more sources than this version. The following were intentionally omitted for v1:

- IACR (mentioned in README)
- PMC / CORE / EuropePMC / dblp / OpenAIRE / CiteSeerX / DOAJ / BASE / Zenodo / HAL / SSRN / Unpaywall / IEEE / ACM

These can be added as needed. PRs welcome!
