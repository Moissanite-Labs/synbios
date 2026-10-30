# SYM-3 project site

Static HTML/CSS (no framework). Edit `index.template.html` and `styles.css`, then:

```sh
make site-build   # writes index.html with ?v=<git short sha> on assets
python3 -m http.server --directory site
```

Open `http://127.0.0.1:8000/index.html`.
