So You Want to Write a DataFrame Viewer
========================================

You want to write a better viewer for tabular data. That's great, the
world needs better interfaces in this space, and there is so much that
can be improved on. Here are some of the biggest design decisions and
their potential side effects, along with projects that chose different
routes. There are many closed source data table viewers with various
levels of capability. It seems like every new notebook hosting
environment feels compelled to build their own dataframe viewer. In this
article I will draw on my own experience creating Buckaroo, as well as
observations from looking at popular open source table viewers like
Perspective, Great Tables, DTale, Hytable, marimo, iTables, and
iPydatagrid.

I have run into each one of these issues while building buckaroo.


Use-case questions
-------------------

Before starting, think about what use case you are looking to solve for.
Are you trying to build tables for relatively static display (PDF to
Huggingface data browser)? Do you want to serve dashboards (a limited
set of interactions with users willing to customize heavily and
specifically for styling)? Do you want to facilitate interactive use in
an IDE like environment (VSCode notebooks, some internal data bench)? Do
you want to work in notebook environments? What size datasets do you
expect your users to work with? What performance expectations do your
users have? Do you want users to be able to customize the experience?
Without writing JS? Do you want to deal with streaming data? Do you want
to allow editing of data?


Processing: server-side or browser-based
-----------------------------------------

The biggest decision to make when building a table viewer is what to do
with the data. Do you want the entire dataset to reside in the browser
or do you want to leave it on the server and page the currently viewed
section back and forth to the browser. Both approaches have their place.

Browser based approaches are much cheaper to serve at scale. Browsers
have improved significantly in the past decade and there are many
applications that put over a gigabyte of data into the browser with no
ill effects. Further with HTTP range requests, the full dataset doesn't
even have to be loaded at once. Apache Arrow and Parquet make this
approach more performant and attractive. This approach scales with little
cost because S3 and Cloudflare are incredibly performant and inexpensive
compared to spinning up server infrastructure.

Browser based approaches fall down with datasets over 1 GB. Additionally
1 GB is about the total limit of memory use that you want a single page
to have, so if you have multiple dataframes that you want to display
simultaneously, keep that in mind. Finally, browser based solutions
require using browser based analytics engines instead of familiar tools
like pandas and polars. Apache Arrow is packageable into a WebAssembly
module, but packaging it into a JS build is tricky.

Server based solutions are more familiar as traditional web apps,
sometimes with some twists. Server based solutions excel for very large
datasets that are backed by analytics engines. If your 10 GB table is
already in a relational database, let the database do the sorting, and
only send over the limited rows that are being displayed. Server based
solutions with persistent connections also allow many more tables to be
displayed simultaneously while limiting browser memory usage. If you have
infrastructure built around analytics pipelines in traditional
environments, server side solutions are often the better way to go.
Sorting and histograms in particular can be hard to implement identically
in different numerical engines.

The downsides of a server based approach are that you always need to have
the server running to make the table work. At the small end this means
you can't simply host an artifact with your table in it. You can't serve
a Jupyter notebook statically in a GitHub repo. If you intend to host an
analytics system with your table, you now need server infrastructure to
back it. Server infrastructure connected to a relational database or
data warehouse is one level of expense — it is even more expensive (in
terms of memory and CPU) to host Python-based analytics server-side.


Serializing data
-----------------

For buckaroo, serializing data to JSON was the slowest part of the
initial render (not true anymore, because of better lazy fetching).
Serializing dataframes is hard. There are multiple numerical Python
(Arrow, computation) concepts that don't have direct equivalents in JS
or JSON. Notably infinity and NaN aren't valid in JSON. Furthermore
datetime handling across JSON requires a processing layer — you will
either encode strings or millisecond offsets, either requiring a metadata
layer that can then be interpreted. Then there are common Python
datatypes like timedelta that have no native JS equivalent.

Next we get to the difficulty of serializing pandas data structures.
Pandas indexes which apply to rows and columns occur in a variety of
formats. Multi-level indexes can be challenging for display — they have
to be special-cased in your display code regardless of how they are
serialized. Pandas columns can also be named in a variety of ways,
including as numerics or strings.

These different dataframe configurations are challenging because they are
hard to completely anticipate. In my experience, when a user constructed
a dataframe with an unexpected structure, it was one of the most likely
things to blow up buckaroo with a JS typing error. There were also
exceptions thrown through most of the pandas processing code.

Polars is a bit easier in this regard. Polars eschews having an index.

Many of these issues exist when serializing to a binary format like
Feather or Parquet, but are a bit different. With Feather/Parquet, make
sure Python objects and lists serialize properly. Also if you want a
single-file static HTML export to work, you will need to base64 encode
the binary data. True binary-to-binary transfer requires a network
connection.


The table viewer component
---------------------------

There are many table components, so much so that there is a site
dedicated to tracking their popularity. Increasing in complexity you
have everything from static HTML, to jQuery-based libraries, to modern
table grids, to AG-Grid, to extreme custom-coded frontend libraries.
HTML-based tables allow simple customizability along with a great story
for static export to the widest list of targets. jQuery-based libraries
(limited table rows, pagination) are relatively simple to use and limit
complexity — previously they were much easier to package into the Jupyter
frontend environment than full JS build chains.

Then there are modern table libraries that aren't AG-Grid. React-data-grid,
angular-grid, tanstack-table, handsome-table. These libraries might be
familiar. They have a straightforward licensing story. They also tend to
have rough edges, limited adoption, and they tend to be abandoned. I
haven't investigated these packages as much.

Next up is AG-Grid. AG-Grid is the reliable gold standard for tables,
under active development for over a decade. AG-Grid has a full
commercial company behind it, along with a permissively licensed
community edition. From my experience they haven't kneecapped the
community edition in favor of the commercial edition, and aim to have
the community edition as the best free table widget on the market. The
tool is extensively documented with working examples. The company is
completely unresponsive to bug reports from non-paying users in my
experience. I chose AG-Grid after listening to an interview with their
founder on the JS Jabber podcast.

Then there are custom table widgets like Perspective, glide-data-grid,
and whatever you cooked up yourself. Perspective has a very impressive
table, and I suspect it has better performance than AG-Grid. It is
minimally documented and doesn't have the wide community adoption that
generates Stack Overflow guidance. glide-data-grid is an impressive
piece of software, rendering to canvas. It also looks like it is falling
into non-maintenance with no commits in the last 10 months.

If you are writing your own table, congrats. You will have ultimate
control over your user experience. You won't have to worry about
dependencies on ``isEven`` or other npm trash. You will have a very
complex core piece to maintain. At a minimum I'd recommend thoroughly
investigating other widgets to see how they approached problems.


The notebook environment
-------------------------

There are many different notebook environments. Jupyter Notebook, Google
Colab, VSCode notebooks, classic notebooks (before Notebook 7.0),
Marimo, Jupyter running on WASM (JupyterLite). All have slight
differences that become especially significant for frontend code.
Styling works differently, loading JavaScript is a bit different.
Anywidget was developed to make all of this easier, and it does. Before
anywidget, this section would have been much longer.

Even determining what environment you are running in is challenging.
This will come up when users file bugs. `widget_utils.py
<https://github.com/paddymul/buckaroo/blob/main/buckaroo/widget_utils.py#L139-L169>`_
is my function for determining which Jupyter environment I'm running in.


Other questions
----------------

**Do you want to enable editing tables?** It isn't too challenging to
enable frontend edits to modify the core dataframe of a table. But then
what? For a full fledged application, you have a bunch of options. In the
Jupyter notebook, you don't have many good options. Accessing widget
state in a Jupyter notebook is possible, but it isn't obvious. Jupyter
notebooks also make it easy to inadvertently rerun a cell — which would
cause your user to lose all edits — a very frustrating experience.

**What about events and callbacks?** Adding click handling events plumbed
through to Python is an attractive option. But now your users have to
make sure they don't have cycles in the event handlers. This is another
place where building a tool for a Jupyter widget is different than
building a tool for a framework or dashboard.


Conclusion
-----------

I'm not suggesting that you avoid creating a table for the Jupyter
environment. I am suggesting that you understand how broad a task it is,
and the ways it could fail.


Comparison of open source DataFrame viewers
---------------------------------------------

.. list-table::
   :header-rows: 1
   :widths: 15 12 10 10 12 10 15 12

   * - Name
     - Server / Browser
     - JSON / Numeric
     - Static Export
     - Jupyter Compatible
     - Dynamic
     - Table Viewer
     - Built on Anywidget?
   * - Buckaroo
     - Server
     - Numeric
     - No
     - Yes
     - Yes
     - AG-Grid
     - Yes
   * - IPYdatagrid
     - Server
     - JSON
     - No?
     - Yes
     - Yes
     - Custom
     - No
   * - Perspective
     - Browser
     - Numeric
     - Yes
     - No?
     - Yes
     - Custom
     - No
   * - iTables
     - Browser
     - JSON
     - Yes
     - Yes
     - No
     - datatables (jQuery based)
     - No
   * - Great Tables
     - Browser
     - HTML
     - Yes
     - Yes
     - No
     - HTML
     - No
   * - DTale
     - Server
     - JSON?
     - No?
     - Yes
     - Yes
     - Custom
     - No
   * - Mito
     - Server
     - JSON
     - No
     - Yes
     - Yes
     - Custom
     - No
   * - Marimo
     - Server
     - JSON?
     - Yes
     - No
     - Yes
     - tanstack-table
     - Yes
