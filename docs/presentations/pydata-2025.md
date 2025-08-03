# Looking at the Data with Buckaroo

## By Paddy Mullen
---


## About me

* Early employee at Anaconda
  * Worked on Wakari (hosted notebook platform for IPython Notebooks)
  * Core contributor to the Bokeh Charting Library
* Quant Dev at various hedge funds
* Long time user of pandas and DataFrames
* Worked at Flatfile on self serve data cleaning tools

---

## Agenda

* The minimum checks I do on each new dataset
* Buckaroo Feature Tour
  * Demonstrating customizations (summary stats, styling, post processing)
  * Low Code UI
  * Auto Cleaning
  * Applications built on top of Buckaroo
* Customizing Buckaroo - Why and When
* Architectural overview of Buckaroo

---

## Looking at a simple dataframe

* Citibike trip data
* ```
     import pandas as pd
     import buckaroo 
   ```
* Note we aren't typing `df.head` or looking up `pd.set_options()`
* All of this in a single cell, we aren't cluttering the notebook

---

## Why I built Buckaroo

* Frustration with simple tasks like looking at the data
* Why name it Buckaroo
* Hard to write reusable dataframe functions
* This should exist


---

## Buckaroo Feature Tour
* Speed - why it matters
* Polars
* Different Notebook environments
* Dastardly DataFrame Dataset 
* Post Processing Functions [![Extending Buckaroo](https://www.gstatic.com/youtube/img/creator/yt_studio_logo_v2_darkmode.svg "Extending Buckaroo")](https://www.youtube.com/watch?v=GPl6_9n31NE)
* Custom Summary Stats  [Extending Buckaroo Notebook](https://paddymul.github.io/buckaroo-examples/lab/index.html?path=Extending.ipynb) 
* [Styling Gallery](
https://marimo.io/p/@paddy-mullen/buckaroo-styling-gallery) [![Styling Buckaroo Video](https://www.gstatic.com/youtube/img/creator/yt_studio_logo_v2_darkmode.svg "Styling Buckaroo")](https://www.youtube.com/watch?v=cbwJyo_PzKY)

* Low Code UI [JLisp Live Notebook](https://marimo.io/p/@paddy-mullen/jlisp-in-buckaroo) [![JLisp Explained](https://www.gstatic.com/youtube/img/creator/yt_studio_logo_v2_darkmode.svg "Buckaroo JLisp explained")](https://youtu.be/3Tf3lnuZcj8)
* Auto Cleaning - without LLMs [Autocleaning Notebook](
https://marimo.io/p/@paddy-mullen/buckaroo-auto-cleaning) [![Autocleaning in depth](https://www.gstatic.com/youtube/img/creator/yt_studio_logo_v2_darkmode.svg "Buckaroo Autocleaning in depth")](https://youtu.be/A-GKVsqTLMI)
* Applications built on top of Buckaroo [Compare Tool Live Marimo](https://marimo.io/p/@paddy-mullen/buckaroo-compare-preview) [![Buckaroo Compare tool video](https://www.gstatic.com/youtube/img/creator/yt_studio_logo_v2_darkmode.svg "Buckaroo Compare tool video")](https://youtube.com/shorts/u3PW6q36ufo)

---

## Customizing Buckaroo


* Philosophy of multiple views on the same data
* Multiple views allows opinionated analysis
* Typing the same commands or waiting for LLMs should bother you
* There are multiple ways of accomplishing things with Buckaroo

---

## Arctitectural overview

* AG-grid table, with declarative langauge
* Python anywidget backend, lazy loading with parquet
* Features not in Buckaroo
  * No event handlers
  * No data editting
  * No rounded corners
  
---

## Conclusion

* Look at the data, Don't use `df.head()`
* `pip install buckaroo`
* Give [https://github.com/paddymul/buckaroo](https://github.com/paddymul/buckaroo) a star on github 
* Get in touch [paddy@paddymullen.com](mailto:paddy@paddymullen.com)
