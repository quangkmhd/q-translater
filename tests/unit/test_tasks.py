import threading, time, unittest
from qtranslate.tasks.types import TaskRequest, TaskResult
from qtranslate.tasks.controller import TaskController
from tests.fixtures.clock import FakeClock


class TasksTests(unittest.TestCase):
    def setUp(self):
        self.clock = FakeClock()
        self.events = []
        self.release = threading.Event()
        self.started = threading.Event()

        def runner(req, settings, deadline, cancelled, update):
            self.started.set()
            self.release.wait(1)
            return TaskResult(req.id, req.action, "ready", "English")

        self.controller = TaskController(runner, self.events.append, self.clock)

    def tearDown(self):
        self.release.set()
        self.controller.shutdown()

    def test_latest_rewrite_owns_copy(self):
        self.controller.submit(TaskRequest("a", "rewrite", text="A"))
        self.started.wait(1)
        self.controller.submit(TaskRequest("b", "rewrite", text="B"))
        self.controller.confirm_copy("a", True)
        self.assertFalse(self.controller.is_current("a"))
        self.assertTrue(self.controller.is_current("b"))
        self.assertFalse(any(e.id == "a" and e.state == "success" for e in self.events))

    def test_actions_have_independent_generation(self):
        self.controller.submit(TaskRequest("a", "rewrite", text="A"))
        self.controller.submit(TaskRequest("b", "translate", text="B"))
        self.assertTrue(self.controller.is_current("a"))

    def test_stream_has_no_copy_or_success(self):
        self.controller.submit(TaskRequest("a", "rewrite", text="A"))
        self.started.wait(1)
        self.controller.update(TaskResult("a", "rewrite", "streaming", "Part"))
        self.assertEqual(self.events[-1].state, "streaming")
        self.controller.confirm_copy("a", True)
        self.assertEqual(self.events[-1].state, "streaming")

    def test_watchdog_expires_even_when_runner_stalls(self):
        self.controller.submit(TaskRequest("a", "rewrite", text="A"))
        self.started.wait(1)
        self.clock.advance(30)
        self.controller.tick()
        self.assertEqual(self.events[-1].error_code, "TASK_TIMEOUT")
        self.controller.update(TaskResult("a", "rewrite", "ready", "Late"))
        self.assertEqual(self.events[-1].state, "error")

    def test_empty_source_does_not_call_runner(self):
        self.controller.submit(TaskRequest("a", "rewrite", text="  "))
        self.assertFalse(self.started.is_set())
        self.assertEqual(self.events[-1].error_code, "NO_SELECTION")

    def test_settings_snapshot(self):
        self.controller.settings = {"prompt_text": "old"}
        self.controller.submit(TaskRequest("a", "rewrite", text="A"))
        self.controller.settings["prompt_text"] = "new"
        self.assertEqual(self.controller.snapshot("a")["prompt_text"], "old")

    def test_repeated_shortcuts_bound_workers(self):
        for n in range(40):
            self.controller.submit(TaskRequest(str(n), "rewrite", text="A"))
        self.assertLessEqual(self.controller.active_workers, 2)
        self.assertLessEqual(self.controller.pending_count, 3)
        self.assertTrue(self.controller.is_current("39"))

    def test_transfer_time_does_not_reset_task_deadline(self):
        self.clock.advance(10)
        self.controller.submit(
            TaskRequest("transfer", "rewrite", text="Hello", started_at=0)
        )
        self.clock.advance(20)
        self.controller.tick()
        self.assertEqual(self.events[-1].error_code, "TASK_TIMEOUT")

    def test_repeated_empty_requests_do_not_retain_source_records(self):
        for n in range(100):
            self.controller.submit(TaskRequest(str(n), "rewrite", text=" "))
        self.assertLessEqual(len(self.controller._records), 3)

    def test_missing_pruned_snapshot_has_safe_defaults(self):
        self.assertEqual(self.controller.snapshot("pruned"), {})
