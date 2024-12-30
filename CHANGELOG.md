# Changelog

## 0.8.0 2024-12-27
This is a big release that changes the JS build flow to be based on anywidget.  Anywidget should provide greater compatability with other notebook like environments such as Google Colab, VS Code notebooks, and marimo.

It also moves the js code to `packages/buckaroo_js_core` This is a regular react js component library built with vite.  This should make it easier for JS devs to understand buckaroo.

None of the end user experience should change with this release.

