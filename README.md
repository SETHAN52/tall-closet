# Tall Closet

A private-ish family catalog of **tall-size clothing** (men's and women's) gathered from public store product feeds and shown on one searchable page.

This is not a store. Every item links out to the retailer's own product page. Names, photos, and prices belong to those stores and can change.

## Site

Unlisted on purpose: `robots.txt` disallows crawlers and the page sends `noindex, nofollow`. Do not link it from other public family sites.

## Refresh

GitHub Actions runs `scripts/fetch_catalog.py` daily and also accepts `workflow_dispatch`. Scheduled GitHub cron has been unreliable on this account, so a cron-job.org trigger of `workflow_dispatch` is the reliable option.

The script reads each store's public Shopify `products.json` or `collections/{handle}/products.json`. It does not scrape HTML. Stores that block bots or disallow crawling in `robots.txt` are skipped.

## Local run

```bash
python3 scripts/fetch_catalog.py
```

Then open `index.html` via any static file server (the page loads `data/items.json`).
