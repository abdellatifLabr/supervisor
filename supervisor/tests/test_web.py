import unittest

from supervisor.process import ProcessStates
from supervisor.tests.base import DummySupervisor
from supervisor.tests.base import DummyRequest
from supervisor.tests.base import DummyPConfig
from supervisor.tests.base import PopulatedDummySupervisor

class DeferredWebProducerTests(unittest.TestCase):
    def _getTargetClass(self):
        from supervisor.web import DeferredWebProducer
        return DeferredWebProducer

    def _makeOne(self, request, callback):
        producer = self._getTargetClass()(request, callback)
        return producer

    def test_ctor(self):
        request = DummyRequest('/index.html', [], '', '')
        callback = lambda *x: None
        callback.delay = 1
        producer = self._makeOne(request, callback)
        self.assertEqual(producer.callback, callback)
        self.assertEqual(producer.request, request)
        self.assertEqual(producer.finished, False)
        self.assertEqual(producer.delay, 1)

    def test_more_not_done_yet(self):
        request = DummyRequest('/index.html', [], '', '')
        from supervisor.http import NOT_DONE_YET
        callback = lambda *x: NOT_DONE_YET
        callback.delay = 1
        producer = self._makeOne(request, callback)
        self.assertEqual(producer.more(), NOT_DONE_YET)

    def test_more_finished(self):
        request = DummyRequest('/index.html', [], '', '')
        callback = lambda *x: 'done'
        callback.delay = 1
        producer = self._makeOne(request, callback)
        self.assertEqual(producer.more(), None)
        self.assertTrue(producer.finished)
        self.assertEqual(producer.more(), '')

    def test_more_exception_caught(self):
        request = DummyRequest('/index.html', [], '', '')
        def callback(*arg):
            raise ValueError('foo')
        callback.delay = 1
        producer = self._makeOne(request, callback)
        self.assertEqual(producer.more(), None)
        logdata = request.channel.server.logger.logged
        self.assertEqual(len(logdata), 1)
        logged = logdata[0]
        self.assertEqual(logged[0], 'Web interface error')
        self.assertTrue(logged[1].startswith('Traceback'), logged[1])
        self.assertEqual(producer.finished, True)
        self.assertEqual(request._error, 500)

    def test_sendresponse_redirect(self):
        request = DummyRequest('/index.html', [], '', '')
        callback = lambda *arg: None
        callback.delay = 1
        producer = self._makeOne(request, callback)
        response = {'headers': {'Location':'abc'}}
        result = producer.sendresponse(response)
        self.assertEqual(result, None)
        self.assertEqual(request._error, 301)
        self.assertEqual(request.headers['Content-Type'], 'text/plain')
        self.assertEqual(request.headers['Content-Length'], 0)

    def test_sendresponse_withbody_and_content_type(self):
        request = DummyRequest('/index.html', [], '', '')
        callback = lambda *arg: None
        callback.delay = 1
        producer = self._makeOne(request, callback)
        response = {'body': 'abc', 'headers':{'Content-Type':'text/html'}}
        result = producer.sendresponse(response)
        self.assertEqual(result, None)
        self.assertEqual(request.headers['Content-Type'], 'text/html')
        self.assertEqual(request.headers['Content-Length'], 3)
        self.assertEqual(request.producers[0], 'abc')

class UIHandlerTests(unittest.TestCase):
    def _getTargetClass(self):
        from supervisor.web import supervisor_ui_handler
        return supervisor_ui_handler

    def _makeOne(self):
        supervisord = DummySupervisor()
        handler = self._getTargetClass()(supervisord)
        return handler

    def test_handle_request_no_view_method(self):
        request = DummyRequest('/foo.css', [], '', '', {'PATH_INFO':'/foo.css'})
        handler = self._makeOne()
        data = handler.handle_request(request)
        self.assertEqual(data, None)

    def test_handle_request_default(self):
        request = DummyRequest('/index.html', [], '', '',
                               {'PATH_INFO':'/index.html'})
        handler = self._makeOne()
        data = handler.handle_request(request)
        self.assertEqual(data, None)
        self.assertEqual(request.channel.producer.request, request)
        from supervisor.web import StatusView
        self.assertEqual(request.channel.producer.callback.__class__,StatusView)

    def test_handle_request_index_html(self):
        request = DummyRequest('/index.html', [], '', '',
                               {'PATH_INFO':'/index.html'})
        handler = self._makeOne()
        handler.handle_request(request)
        from supervisor.web import StatusView
        view = request.channel.producer.callback
        self.assertEqual(view.__class__, StatusView)
        self.assertEqual(view.context.template, 'ui/status.html')

    def test_handle_request_tail_html(self):
        request = DummyRequest('/tail.html', [], '', '',
                               {'PATH_INFO':'/tail.html'})
        handler = self._makeOne()
        handler.handle_request(request)
        from supervisor.web import TailView
        view = request.channel.producer.callback
        self.assertEqual(view.__class__, TailView)
        self.assertEqual(view.context.template, 'ui/tail.html')

    def test_handle_request_ok_html(self):
        request = DummyRequest('/tail.html', [], '', '',
                               {'PATH_INFO':'/ok.html'})
        handler = self._makeOne()
        handler.handle_request(request)
        from supervisor.web import OKView
        view = request.channel.producer.callback
        self.assertEqual(view.__class__, OKView)
        self.assertEqual(view.context.template, None)

    def test_continue_request_preserves_selected_processes(self):
        request = DummyRequest('/index.html', [], '', '',
                               {'PATH_INFO':'/index.html'})
        handler = self._makeOne()
        handler.continue_request(
            'process=foo%3Abar&process=baz&action=startselected', request)
        view = request.channel.producer.callback
        self.assertEqual(view.context.form['action'], 'startselected')
        self.assertEqual(view.context.form['process'], ['foo:bar', 'baz'])


class StatusViewTests(unittest.TestCase):
    def _getTargetClass(self):
        from supervisor.web import StatusView
        return StatusView

    def _makeOne(self, context):
        klass = self._getTargetClass()
        return klass(context)

    def _makePopulatedSupervisor(self):
        options = DummySupervisor().options
        pconfig1 = DummyPConfig(options, 'device1', '/bin/device1')
        pconfig2 = DummyPConfig(options, 'device2', '/bin/device2')
        supervisord = PopulatedDummySupervisor(options, 'devices',
                                               pconfig1, pconfig2)
        for process in supervisord.process_groups['devices'].processes.values():
            process.group = supervisord.process_groups['devices']
        return supervisord

    def test_make_callback_noaction(self):
        context = DummyContext()
        context.supervisord = DummySupervisor()
        context.template = 'ui/status.html'
        context.form = {}
        view = self._makeOne(context)
        self.assertRaises(ValueError, view.make_callback, 'process', None)

    def test_render_noaction(self):
        context = DummyContext()
        context.supervisord = DummySupervisor()
        context.template = 'ui/status.html'
        context.request = DummyRequest('/foo', [], '', '')
        context.form = {}
        context.response = {}
        view = self._makeOne(context)
        data = view.render()
        self.assertTrue(data.startswith('<!DOCTYPE html PUBLIC'), data)
        self.assertIn('id="selected-count">0 selected<', data)
        self.assertIn("document.getElementById('selected-count')", data)

    def test_render_refresh(self):
        context = DummyContext()
        context.supervisord = DummySupervisor()
        context.template = 'ui/status.html'
        context.response = {}
        context.form = {'action':'refresh'}
        view = self._makeOne(context)
        data = view.render()
        from supervisor.http import NOT_DONE_YET
        self.assertTrue(data is NOT_DONE_YET, data)

    def test_make_callback_startselected_without_selection(self):
        context = DummyContext()
        context.supervisord = DummySupervisor()
        context.template = 'ui/status.html'
        context.form = {}
        view = self._makeOne(context)
        callback = view.make_callback(None, 'startselected')
        self.assertEqual(callback(), 'No processes selected for start')

    def test_make_callback_startselected_mixed_results(self):
        context = DummyContext()
        context.supervisord = self._makePopulatedSupervisor()
        context.template = 'ui/status.html'
        context.form = {'process': ['devices:device1', 'devices:device2']}
        view = self._makeOne(context)
        context.supervisord.set_procattr('device1', 'state', ProcessStates.STOPPED)
        context.supervisord.set_procattr('device2', 'state', ProcessStates.RUNNING)
        callback = view.make_callback(None, 'startselected')
        self.assertEqual(
            callback(),
            'Started 1 of 2 selected processes; failures: '
            'devices:device2 (already started)')

    def test_render_startselected_redirects_with_message(self):
        context = DummyContext()
        context.supervisord = self._makePopulatedSupervisor()
        context.template = 'ui/status.html'
        context.request = DummyRequest('/foo', [], '', '')
        context.response = {'headers': {}}
        context.form = {
            'action': 'startselected',
            'process': ['devices:device1'],
            'SERVER_URL': 'http://example.com',
            }
        context.supervisord.set_procattr('device1', 'state', ProcessStates.STOPPED)
        view = self._makeOne(context)

        from supervisor.http import NOT_DONE_YET
        data = view.render()
        self.assertTrue(data is NOT_DONE_YET, data)

        data = view.render()
        self.assertTrue(data.startswith('<!DOCTYPE html PUBLIC'), data)
        self.assertEqual(
            context.response['headers']['Location'],
            'http://example.com/?message=Started%201%20selected%20process')

class DummyContext:
    pass
