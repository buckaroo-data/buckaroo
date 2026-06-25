"""End-to-end test for the server telemetry sink (#943).

``buckaroo.server.telemetry.make_http_sink`` POSTs each span record to the
companion on the Tornado IOLoop (``AsyncHTTPClient`` + ``spawn_callback``) — no
background threads. This stands up a receiver on the test's own IOLoop and
asserts that a span emitted through the sink actually arrives as JSON.
"""
import json

import tornado.gen
import tornado.testing
import tornado.web

from buckaroo.pluggable_analysis_framework import perf_log
from buckaroo.server import telemetry


class _Receiver(tornado.web.RequestHandler):
    def post(self):
        self.settings["received"].append(json.loads(self.request.body))
        self.set_status(200)


class TestTelemetrySink(tornado.testing.AsyncHTTPTestCase):
    def get_app(self):
        self.received: list = []
        return tornado.web.Application(
            [(r"/internal/telemetry", _Receiver)], received=self.received)

    @tornado.testing.gen_test
    async def test_make_http_sink_posts_record_over_ioloop(self):
        sink = telemetry.make_http_sink(self.get_url("/internal/telemetry"))
        with perf_log.telemetry_context("sess-http", sink, source="server"):
            with perf_log.perf_span("firstpull.metadata") as span:
                span.set_attr(cache_status="miss")

        # The POST was scheduled with spawn_callback; yield to the loop until
        # the receiver records it. No threads, so this is the only wait needed.
        for _ in range(100):
            if self.received:
                break
            await tornado.gen.sleep(0.02)

        self.assertEqual(len(self.received), 1)
        r = self.received[0]
        self.assertEqual(r["name"], "firstpull.metadata")
        self.assertEqual(r["trace"], "sess-http")
        self.assertEqual(r["source"], "server")
        self.assertEqual(r["attrs"]["cache_status"], "miss")
