# Publishing to GitHub Wiki

Matrix-Art keeps wiki-style documentation under:

```text
docs/wiki/
```

This is easy to version with the main repository. GitHub also has a separate built-in Wiki feature. You can use either approach.

## Option 1: keep docs in the repo

This is the simplest option.

Commit the `docs/wiki/` folder:

```bash
git add docs/wiki README.md
git commit -m "Add Matrix-Art wiki documentation"
git push
```

Users can browse the pages directly on GitHub.

## Option 2: copy to GitHub Wiki

GitHub Wiki is a separate Git repository ending in `.wiki.git`.

Clone it next to your main repo:

```bash
cd ~/Downloads
git clone https://github.com/Charlie22911/Matrix-Art.wiki.git Matrix-Art.wiki
```

Copy the Markdown files:

```bash
cp ~/Downloads/Matrix-Art/docs/wiki/*.md ~/Downloads/Matrix-Art.wiki/
cd ~/Downloads/Matrix-Art.wiki
git add .
git commit -m "Add Matrix-Art wiki pages"
git push
```

GitHub's Wiki homepage normally uses `Home.md`. If you want the wiki index to be the home page, copy `README.md` as `Home.md`:

```bash
cp ~/Downloads/Matrix-Art/docs/wiki/README.md ~/Downloads/Matrix-Art.wiki/Home.md
```

## Recommended approach

Keep `docs/wiki/` in the main repo. Optionally mirror it to GitHub Wiki when you want the dedicated Wiki tab to be populated.
