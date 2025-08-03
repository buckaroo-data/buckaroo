to build the pydata presenation run

```sh
npx @marp-team/marp-cli@latest slide-deck.md -o output.html
npx @marp-team/marp-cli@latest pydata-2025.md -o ../extra-html/pydata-boston-2025.html
```

to watch the presentations run
```sh
npx @marp-team/marp-cli@latest -w pydata-2025.md
```
and in another shell run

```sh
npx http-server -o ./
```


