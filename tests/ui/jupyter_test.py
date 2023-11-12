import playwright.sync_api
from IPython.display import display


'''
def test_widget_aggrid(ipywidgets_runner, page_session: playwright.sync_api.Page, assert_solara_snapshot):
    def kernel_code():
        import ipyaggrid
        cars = [
            {"carName": "Chevelle", "origin": "US", "make": "Chevrolet", "price": 30415},
            {"carName": "Skylark 320", "origin": "US", "make": "Buick", "price": 21042},
            {"carName": "PL411", "origin": "Asia", "make": "Datsun", "price": 27676},
        ]
        column_defs = [{"field": c} for c in cars[0]]

        grid_options = {
            "columnDefs": column_defs,
        }
        g = ipyaggrid.Grid(grid_data=cars, grid_options=grid_options)

        display(g)
    ipywidgets_runner(kernel_code)
    cell = page_session.locator(".ag-root-wrapper >> text=Chevrolet")
    cell.click()
    cell.wait_for()
    assert_solara_snapshot(page_session.locator(".ag-root-wrapper").screenshot())
'''
def test_widget_buckaroo(ipywidgets_runner, page_session: playwright.sync_api.Page, assert_solara_snapshot):
    def kernel_code():
        import buckaroo
        import pandas as pd
        df = pd.DataFrame({"carName": ["Chevelle", "Skylark", "PL411"],
                           "origin": ["US", "US", "asia"],
                           "make": ["Chevrolet", "Buick", "Datsun"]
                           })
        bw = buckaroo.BuckarooWidget(df)
        display(bw)
    ipywidgets_runner(kernel_code)
    cell = page_session.locator(".df-viewer >> text=Chevrolet")
    cell.click()
    cell.wait_for()
    page_session.locator(".df-viewer").screenshot()
    #assert_solara_snapshot(page_session.locator(".df-viewer").screenshot())

