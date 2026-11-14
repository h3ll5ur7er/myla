# The Myla website

Myla's home on the web (D208): the landing page, the language docs and the standard library's reference generated from this repository, a playground, and the course of `../learn/`, all running the real checker and interpreter in the browser.

```bash
../scripts/bootstrap.sh        # the toolchain the build uses (build/myla)
npm ci
npm start                      # http://localhost:4200
npm test                       # the content pipeline's tests and the app's unit tests
npm run build:pages            # dist/ for GitHub Pages (/myla/)
npm run e2e                    # the built site in Chromium
npm run check-course           # every exercise through play.wasm
```

How it is built, where its content comes from and how it is tested and deployed: [docs/Architecture/Website.md](../docs/Architecture/Website.md).
