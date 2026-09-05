# LEHAR | Landing Page

Static landing page for LEHAR (premium red chilli powder by Vijaylaxmi Trading Company, Gadag, Karnataka). Vanilla HTML, CSS, JavaScript. No build step.

## Files

```
landing/
├── index.html
├── styles.css
├── script.js
└── README.md
```

References brand assets from the parent `../assets/` folder (logo, favicon). If you copy `landing/` somewhere else, copy `assets/` next to it or update the paths in `index.html`.

## Run locally

```bash
# Landing page
cd landing
python -m http.server 7890        # then open http://localhost:7890

# Streamlit app (separate terminal)
cd ..
streamlit run app/dashboard.py   # then open http://localhost:8501
```

The "Open the app" button points at the deployed Streamlit app: <https://lehar-chilli-sales.streamlit.app>.

## Deploy

Vercel, Netlify, and GitHub Pages are all drop-in. The `index.html` already points at the deployed Streamlit app at <https://lehar-chilli-sales.streamlit.app>. If you fork this and use a different Streamlit URL, update the four `lehar-chilli-sales.streamlit.app` references in `index.html` with yours.

```bash
# Vercel
npx vercel --prod

# Netlify
npx netlify deploy --dir=. --prod
```

## Brand tokens

| Token | Value |
| --- | --- |
| Background | `#111418` |
| Surface (light) | `#F5F5F5` |
| Accent | `#D90429` (Crimson) |
| Accent hover | `#EF1B41` |
| Font | Plus Jakarta Sans |

## Accessibility

- Skip link as first focusable element
- Single-line nav at desktop, hamburger at ≤ 768px
- Visible focus rings (crimson) on every interactive element
- `prefers-reduced-motion` disables reveals, transitions, and smooth scroll
- All images have explicit `width`, `height`, and `alt` text
- Color contrast passes WCAG AA for body and AAA for headings
