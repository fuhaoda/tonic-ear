# Tonic Ear GitHub Pages Deployment Guide

This project supports fully static deployment (no backend API required), so it can be hosted directly on GitHub Pages.

Deployment strategy (same as KeyBand):
- Single frontend directory: `docs/`
- Audio assets also live in `docs/assets/audio/`
- GitHub Pages source: `/docs` on the `main` branch

## 1. One-Time Setup

1. Push your repository to GitHub (including `docs/`).
2. Open your repository settings: `Settings` -> `Pages`.
3. Under `Build and deployment`, set:
- `Source`: `Deploy from a branch`
- `Branch`: `main`
- `Folder`: `/docs`
4. Save and wait for the first publish to finish.

Published site URL:

`https://<your-github-username>.github.io/<your-repo-name>/`

## 2. Deployment Workflow After Changes

Run from repository root:

```bash
git add docs app scripts Dockerfile tests README.md GITHUB_PAGES_DEPLOY.md
git commit -m "Update GitHub Pages site"
git push
```

Wait for GitHub Pages to finish republishing (usually 1-3 minutes).

## 3. Local Preview (Using `docs/`)

```bash
python3 -m http.server 8080 --directory docs
```

Open:

`http://127.0.0.1:8080`

## 4. Notes

- `docs/` is the source of truth for frontend and static assets.
- Keep `docs/.nojekyll` committed.
- Keep `docs/CNAME` committed if you use a custom domain.
- Asset URLs are now relative and compatible with GitHub Pages subpaths (`/<repo>/`).
- Question metadata and sessions are generated in the frontend, so `/api/v1` is not required for Pages.

## 5. Troubleshooting

1. Blank page or missing styles  
Verify Pages source is set to `main /docs`, then confirm your latest `docs/` changes were committed and pushed.

2. Audio loading failure  
Most likely the latest `docs/assets/audio` files were not pushed. Commit and push again.

3. Custom domain stops working  
Put your domain in `docs/CNAME`, commit, and push.
