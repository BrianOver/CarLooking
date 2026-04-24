# CarLooking

Scrapes public used-car listings for **manual weekend cars** near Sachse, TX and ranks each one by a worth/risk heuristic. Built for a search under ~$23K with a bias toward aesthetically-interesting manuals (classic Zs, 911s, Miatas, Boxsters, S2000s, E30/E36/E46, RX-7/8, etc.).

Comes with a **local web UI** for filtering, sorting, and browsing the results — see [Web UI](#web-ui) below.

## TODO — fix before next Azure deploy

**GitHub Actions "Deploy to Azure" is currently failing** on every push. Last 2 runs failed in <15s with:

```
Login failed: Using auth-type: SERVICE_PRINCIPAL. Not all values are present.
Ensure 'client-id' and 'tenant-id' are supplied.
```

This is a secrets-config issue only — the code is fine and is already sitting on `main`. Azure App Service is still running the last successfully-deployed commit.

### Fix steps (~5 min)

```bash
# 1. Get your Azure subscription ID
az account show --query id -o tsv

# 2. Create a service principal scoped to the CarLooking resource group
az ad sp create-for-rbac \
  --name carlooking-github \
  --role contributor \
  --scopes /subscriptions/<YOUR_SUB_ID_FROM_STEP_1>/resourceGroups/carlooking-rg \
  --sdk-auth
```

The command prints a JSON blob like `{ "clientId": "...", "clientSecret": "...", "tenantId": "...", "subscriptionId": "...", ... }`.

3. In the GitHub repo, go to **Settings → Secrets and variables → Actions → New repository secret**
4. Create/update secret named exactly `AZURE_CREDENTIALS` — paste the **entire JSON blob** as the value (including the surrounding braces)
5. Confirm `AZURE_WEBAPP_NAME` secret exists and equals `carlooking`
6. Re-run the failed workflow from the Actions tab — should succeed in ~2 min

### Why it broke

The current `AZURE_CREDENTIALS` secret was probably stored as just the client-secret string or a partial publish-profile XML. `azure/login@v2` with `auth-type: SERVICE_PRINCIPAL` requires the full SP JSON schema from `az ad sp create-for-rbac --sdk-auth`.

### Verification after fix

```bash
gh run list --workflow=deploy-azure.yml --limit 1    # should show "completed success"
curl -s -o /dev/null -w "%{http_code}\n" https://carlooking.azurewebsites.net/
# expect 200 (or 302 to /login if auth is enabled)
```

---

## Quick start

```bash
pip install -r requirements.txt
python main.py            # scrape + score (takes ~3 min)
python webapp.py          # local UI at http://127.0.0.1:5173/
```

That's it. The UI lets you sort by distance / price / year, filter by verdict / source / budget / mileage, and click into any listing for full details + a link to the original.

## Cloud deployment (Azure App Service)

Deploy to Azure so the app runs 24/7 independent of your PC. Your phone just needs a browser — no PC, no Tailscale, no local network required.

### One-time setup (~15 min)

**1. Create Azure resources**
```bash
# Install Azure CLI if needed: https://aka.ms/installazurecli
az login

# Create resource group
az group create --name carlooking-rg --location eastus

# Create storage account (for persistent listings)
az storage account create --name carlookingdata --resource-group carlooking-rg --sku Standard_LRS
CONN=$(az storage account show-connection-string --name carlookingdata --resource-group carlooking-rg --query connectionString -o tsv)

# Create App Service plan (Free tier)
az appservice plan create --name carlooking-plan --resource-group carlooking-rg --sku F1 --is-linux

# Create the web app
az webapp create --name carlooking --resource-group carlooking-rg --plan carlooking-plan --runtime "PYTHON:3.12"

# Set startup command
az webapp config set --name carlooking --resource-group carlooking-rg --startup-file startup.sh

# Set environment variables
az webapp config appsettings set --name carlooking --resource-group carlooking-rg --settings \
  CARLOOKING_PASSWORD="your-password-here" \
  SECRET_KEY="$(python -c 'import secrets; print(secrets.token_hex(32))')" \
  AZURE_STORAGE_CONNECTION_STRING="$CONN" \
  AZURE_BLOB_CONTAINER="carlooking" \
  SCRAPE_INTERVAL_HOURS="12"
```

**2. Set up GitHub Actions deployment**
1. In Azure portal → your App Service → Deployment Center → **Get publish profile** → download
2. In GitHub repo → Settings → Secrets → New secret:
   - `AZURE_WEBAPP_NAME` = `carlooking`
   - `AZURE_WEBAPP_PUBLISH_PROFILE` = paste the entire publish profile XML
3. Push to `main` — GitHub Actions deploys automatically

**3. Install as Android PWA**
1. Open Chrome on Android, go to `https://carlooking.azurewebsites.net`
2. Log in with your password
3. Tap 3-dot menu → **Add to Home screen** → **Install**

### How it works in Azure

| Feature | Behavior |
|---|---|
| Listings storage | Azure Blob Storage — survives restarts |
| Auto-scrape | Every `SCRAPE_INTERVAL_HOURS` hours (default 12) |
| Manual refresh | "Refresh data" button in the UI |
| Auth | Password login, 30-day cookie |
| HTTPS | Included free on `*.azurewebsites.net` — PWA service worker works |
| Cost | Free tier (F1): $0/month for personal use |

### Environment variables reference

See [`.env.example`](.env.example) for all variables. Set them in Azure portal → App Service → Configuration → Application settings.

---

## Android app (PWA)

The web UI is installable as a full-screen home-screen app on Android — no Play Store, no APK signing, private by default.

### Option A — Home WiFi only (simplest)

1. Start the webapp: double-click `start.bat`
2. Note the **Network:** URL printed in the console (e.g. `http://192.168.1.42:5173/`)
3. On Android, open **Chrome** and navigate to that URL
4. Tap the 3-dot menu → **Add to Home screen** → **Install**
5. CarLooking appears as a full-screen app on your home screen

### Option B — Anywhere access via Tailscale (recommended)

Tailscale creates a private encrypted network between your PC and phone — works on any network, no port forwarding needed.

1. Install [Tailscale](https://tailscale.com) on your Windows PC and sign in
2. Install [Tailscale](https://play.google.com/store/apps/details?id=com.tailscale.ipn.android) on your Android phone and sign in with the **same account**
3. Find your PC's Tailscale IP: open Tailscale on PC → it shows something like `100.x.x.x`
4. Start the webapp on the PC: `start.bat` (or `start_silent.vbs` for no console)
5. On Android Chrome, navigate to `http://100.x.x.x:5173/`
6. Install as PWA (same as Option A step 4–5)

For full offline caching (optional), enable HTTPS via Tailscale:
```
tailscale cert <your-machine-name>.ts.net
```
Then launch with: `CERT=.ts.net.crt KEY=.ts.net.key python webapp.py` — the service worker at `/service-worker.js` will activate and cache listings for offline viewing.

### Auto-start with Windows

So CarLooking is always running when your PC is on:

1. Press `Win+R`, type `shell:startup`, press Enter
2. Copy `start_silent.vbs` into that folder
3. CarLooking will start silently on every boot; access it from your phone at any time

To stop it: Task Manager → find `pythonw.exe` → End Task.

### PWA shortcut: "Refresh listings"

The installed Android app has a **long-press shortcut** named "Refresh listings" — long-press the home screen icon and tap it to immediately kick off a fresh scrape.

## Sources

Tested against live sites, DFW radius, manual filter:

| Source | Status | Notes |
|---|---|---|
| Craigslist (12 regional sites) | ✅ reliable | Parses JSON-LD on the search page (RSS feeds were deprecated by CL). Covers DFW + East TX + Waco + Texoma + Shreveport + Lawton + OKC + Austin + Houston + Abilene + Tulsa + San Marcos. Yields ~30–70 real listings per run. |
| eBay Motors | ✅ reliable | Public search HTML. Yields ~15–40 per run. Limits to manual + within radius server-side. Per-listing shipping estimate based on seller state. |
| Bring a Trailer | ✅ reliable | Scrapes the bootstrap JSON on `/auctions/`. Nationwide, filtered client-side against your target model list. Fetches detail pages for seller city/state + auction end time. |
| AutoTrader | ⚠️ best-effort | Works on the first request; aggressive anti-bot then rate-limits us. For better yields use Playwright (not wired in by default). |
| Cars & Bids | ⚠️ best-effort | Anon HTML + __NEXT_DATA__ parser — yields vary; some days you get ~10 matches, others zero. |
| ClassicCars.com | ⚠️ opt-in | Off by default. Their search/price filters don't actually filter — most listings are $40K+ muscle cars. Occasionally surfaces a sub-$23K Datsun/VW. Enable if you stretch budget. |
| Hemmings | ⚠️ opt-in | Off by default. Cloudflare JS challenge blocks the search-page URL discovery; detail pages work but we can't reach them without JS. |
| Facebook Marketplace | ⚠️ anon mode only | Low yield without a logged-in Playwright session; Meta ToS means personal use only, do not redistribute. |
| Carvana | ❌ SPA-gated | Scraper code exists but Carvana's SSR only returns recommendation carousels, not actual filtered inventory. Real listings are JS-loaded via their API — needs Playwright. |
| Cars.com | ❌ SPA-gated | Page is client-side-rendered — SSR has shell but not listings. Needs Playwright. |
| CarMax | ❌ SPA-gated | Tested: even their `/api/search/run` endpoint returns HTML wrapper. Needs Playwright. |
| Hagerty Marketplace | ❌ SPA-gated | Uses urql/GraphQL client-side hydration. Listings never appear in SSR. Needs Playwright. |
| CarGurus | ❌ Cloudflare-gated | Blocked even with `curl_cffi` TLS impersonation. Needs Playwright. |
| TrueCar / KBB / AutoHunter / Mecum | ❌ SPA or blocked | Tested, none return real listing data in SSR. |

Each scraper is isolated — if one 403s or breaks, the rest still work. Enable only what you want via `sources:` in `config.yaml`.

Primary reliable yield comes from **Craigslist + eBay Motors + Bring a Trailer** — that combo already surfaces 80–150+ real manual-transmission listings per run across the broader TX/OK area and nationwide auctions.

### Why so many sites are "SPA-gated"

Most modern car-selling platforms (Carvana, CarMax, Cars.com, CarGurus, TrueCar, Hagerty, AutoHunter) render listings client-side via React/Next.js + GraphQL. The initial HTML response is just a shell; real listing data only appears after JavaScript executes and makes authenticated XHR calls to their internal APIs. Pure HTTP scraping can't see it.

To scrape any of these you'd need to:
1. Install Playwright: `pip install playwright && playwright install chromium`
2. Refactor the `base.make_session()` helper to return a Playwright browser context
3. In each scraper, `page.goto(url)` and wait for the listings to render before parsing

The `carvana.py` scraper is structured for this — the `_parse_ld_vehicles()` and `_normalize()` helpers would work unchanged once the page has been JS-rendered.

## Install

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows
# or: source .venv/bin/activate on macOS/Linux

pip install -r requirements.txt
```

### Optional: Facebook Marketplace via Playwright

FB blocks anon scraping hard. If you want to try anyway:

```bash
pip install playwright
playwright install chromium
# then set sources.facebook_marketplace: true in config.yaml
```

On first run, a browser window opens — log in manually. The session persists to `.playwright_fb_profile/` (gitignored) so subsequent runs are automated. Expect this to break periodically when Meta changes their UI.

### Optional: Claude-enriched analysis

```bash
export ANTHROPIC_API_KEY=sk-ant-...
python main.py --llm
```

Uses Claude Haiku for a cheap extra pass over the top 20 listings, adding candid model-specific commentary (known problem areas, typical ownership costs, price sanity).

## Run

```bash
# Dry run — verify config, no network
python main.py --dry-run

# Full scrape with all enabled sources
python main.py -v

# Just Craigslist (fastest, most reliable)
python main.py --source craigslist -v

# Multiple specific sources
python main.py --source craigslist --source cars_com --source ebay_motors
```

Outputs:
- `output/report.html` — static scored HTML report (open directly in a browser)
- `output/listings.json` — raw structured data, consumed by the web UI

Both are gitignored — they contain seller location/contact info.

## Web UI

For browsing, filtering, and searching the results interactively:

```bash
python webapp.py
# opens at http://127.0.0.1:5173/
```

Features:
- **Grid view** of scored listings, sortable by best-match, **distance (closest)**, all-in price, price, year, or mileage
- **Live search** across title, model, location, and description
- **Sidebar filters**: verdict, source, min score, price range, year range, max mileage
- **Price type badges** — every listing shows whether the number is an `ASKING` price, current `BID`, or `SOLD` final price. Lets you spot auction listings (BaT, C&B) at a glance so you don't confuse an opening bid with a real asking price.
- Click any card → **details modal** with full concerns/benefits + direct link to the listing
- **Refresh data** button kicks off a fresh scrape in the background and auto-reloads the grid when done

All filtering happens in the browser — the page loads the JSON file once on startup and never hits the network except for refresh.

## Price type (bid vs asking)

Each listing carries a `price_type`:

| Value | Meaning | Where it comes from |
|---|---|---|
| `asking` | A fixed asking price from a seller | Craigslist, eBay Motors, AutoTrader, Cars.com, ClassicCars, Hemmings |
| `bid` | Current high bid in an active auction (will climb) | Bring a Trailer active auctions, Cars & Bids |
| `sold` | Final hammer price — auction already ended | Bring a Trailer / Cars & Bids completed auctions |
| `auction` | eBay auction listing (distinct from BIN) | reserved for future eBay auction detection |

This matters a lot: a BaT listing showing `$3,900 [BID]` with 2 days to go will probably end at $8–12K. Don't get excited by opening-bid prices.

## Handoff / picking this up later

For future-you or another Claude instance working on this repo:

**Project layout**
- [main.py](main.py) — CLI entry (`python main.py` runs all enabled scrapers, scores, writes `output/`)
- [webapp.py](webapp.py) — Flask UI, self-contained (HTML/CSS/JS inlined in the template string)
- [config.yaml](config.yaml) — budget, zip, radius, target model list, source toggles, red/green flags
- [src/models.py](src/models.py) — `Listing` dataclass (the shared data structure)
- [src/analyzer.py](src/analyzer.py) — scoring heuristic + optional Claude Haiku enrichment
- [src/ac_estimator.py](src/ac_estimator.py) — Texas A/C retrofit cost heuristic
- [src/report.py](src/report.py) — static HTML report + Rich console table
- [src/scrapers/base.py](src/scrapers/base.py) — shared HTTP client (uses `curl_cffi` for Chrome TLS impersonation — critical for bypassing Cloudflare on eBay/AutoTrader/etc.), shared parsers (`parse_price`, `parse_year`, `parse_mileage`, `detect_transmission`, `title_matches_model`)
- [src/scrapers/*.py](src/scrapers/) — one file per site; each exposes a `scrape(criteria, target_models) -> list[Listing]` function; registered in [src/scrapers/\_\_init\_\_.py](src/scrapers/__init__.py)

**Key design decisions**
- **`curl_cffi` for HTTP**: plain `requests` gets 403'd by Cloudflare on most car sites. `curl_cffi` with `impersonate="chrome124"` does real Chrome TLS fingerprinting and gets past. If a site starts blocking again, try a different `impersonate=` value.
- **Scrapers are independent**: one crash won't kill the run. Each is wrapped in try/except in [main.py](main.py).
- **Client-side model filter**: sites like BaT and ClassicCars ignore their own search params. We fetch the full page and match titles against `target_models` locally via `title_matches_model()`. That function guards against generic words like "Roadster" / "Spider" matching every car by requiring the full "Make Model" phrase in those cases.
- **BaT non-car filter**: BaT's bootstrap items include automobilia (wheels, signs, hardtops). We skip any item whose `categories` contains `"379"` or `"380"`.
- **BaT location enrichment**: bootstrap JSON only gives country + lat/lon. For city/state we fetch each matched detail page (capped at ~60/run) and regex out `<strong>Location</strong>: <a>City, State ZIP</a>` from the essentials section.
- **Output is gitignored**: `output/listings.json` + `output/report.html` contain seller PII (names, phone numbers, addresses sometimes). Do not commit. The public GitHub repo is https://github.com/BrianOver/CarLooking.
- **Git identity scoped to this repo**: `user.email = howlb73@gmail.com`, `user.name = BrianOver`. Set locally, not globally, so it doesn't bleed into Fornida work repos.

**Known gaps + future work**
- **AutoTrader rate-limits us** after ~10 requests. Current scraper just tries and logs the 403s. Best fix: wire Playwright with a real Chromium session (or rotate residential proxies, which is overkill for this).
- **Cars.com / Cars & Bids / Facebook Marketplace / CarGurus** all need Playwright. Scraper files exist as stubs ready to be upgraded when someone adds that dependency.
- **Hemmings**: search page is behind a Cloudflare JS challenge so URL discovery returns 0. Detail-page parsing works — if URLs can be obtained another way (sitemap, RSS feed if one exists, Playwright), the detail scraper is ready.
- **No persistent storage of seen listings**: every run is a full snapshot. A future "diff mode" could email the top new listings since last run.
- **No image display in web UI**: `Listing.images` is populated for Craigslist but the UI doesn't render thumbnails yet. Low-hanging addition.
- **ClassicCars pagination loops**: their search ignores pagination, so we only fetch page 1. Enable manually via `config.yaml` if budget stretches to ~$40K.

**To add a new scraper**
1. Create `src/scrapers/<name>.py` with a `scrape(criteria: dict, target_models: list[str]) -> list[Listing]` function
2. Register in `src/scrapers/__init__.py` (`REGISTRY` dict)
3. Add to `config.yaml` under `sources:` (default to `true`/`false`)
4. Use `make_session()` and `polite_get()` from `base.py` — they handle curl_cffi + rate-limiting
5. Use `title_matches_model()` if the site doesn't honor its own search filters
6. Set `price_type="bid"` / `"asking"` / `"sold"` as appropriate on each Listing

**To change criteria**: just edit `config.yaml` — budget, zip, radius, target model list, red/green flags. No code changes needed.

## How scoring works

Each listing starts at 50 and is adjusted:

| Factor | ± |
|---|---|
| Matches a target model | +15 |
| Price within budget | +10 |
| Well under budget (<60%) | +20 |
| Manual transmission confirmed | +5 |
| Close to Sachse | +5 |
| Green flags in description ("clean title", "records", "cold a/c") | +2 each, cap +10 |
| Red flags ("rebuilt", "needs engine", "salvage") | -8 each |
| No price | -10 |
| Transmission mismatch | -25 |
| Outside radius | -10 |
| Missing year/mileage | -3 each |
| A/C needs major work (Texas) | -8 |

Verdict buckets: `strong buy` / `worth a look` / `mixed` / `risky` / `skip`.

## A/C estimator

Since you're in Texas, the scorer estimates A/C retrofit cost based on the car's age and any description keywords:

- Pre-1975: ~$4,000 (Vintage Air aftermarket kit)
- 1975–1992 (R-12 era): ~$2,500 (retrofit to R-134a)
- 1993–2004: ~$1,400 (original components tired)
- 2005+: ~$800 (recharge / compressor)
- Listing says "cold a/c" / "ice cold": $0
- Listing says "no a/c" / "needs a/c": full baseline estimate

The "All-in price" column on the report adds this to the asking price.

## Tuning

Edit `config.yaml` to change:
- Budget (`max_price`, `min_price`)
- Location (`zip_code`, `radius_miles`)
- Target model list
- Red/green flag phrases
- Which sources are enabled
- How many listings show up in the report

## Legal / ToS notes

- Craigslist RSS is explicitly permitted. Everything else is personal-use-scale scraping of public pages. Don't redistribute or commercialize the scraped data.
- Facebook Marketplace scraping is against Meta's ToS. The FB scraper is off by default for a reason; enabling it is at your own risk.
- The output files contain seller locations and sometimes names/phone numbers. `.gitignore` blocks `output/` from being committed. Keep it that way — this is a public repo.
- Never commit `.env`, `cookies.json`, `fb_session.json`, or the `.playwright_fb_profile/` directory. They contain session tokens.

## Disclaimer

Worth/risk scores are heuristic and not a substitute for a pre-purchase inspection. A 95-score '95 Miata can still have bad rockers. Budget a PPI for anything you're serious about.

## License

MIT. Do what you want.
