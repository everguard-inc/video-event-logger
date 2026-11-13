"""Estimate wall-clock work time, without collecting input or per-event history."""
import time


class WorkTimeTracker:
    IDLE_SECONDS = 60.0
    MAX_SAMPLE_GAP = 5.0

    def __init__(self, clock=time.monotonic):
        self.clock = clock
        self.document = None
        self.last_sample = clock()
        self.last_activity = float("-inf")
        self.foreground = False
        self.playing = False

    def attach(self, document):
        # The caller checkpoints the previous document before changing videos.
        self.document = document
        self.last_sample = self.clock()
        self.last_activity = self.last_sample
        self.foreground = False
        self.playing = False

    def sample(self, foreground, playing, activity=False):
        now = self.clock()
        elapsed = now - self.last_sample
        added = 0.0
        if (self.document is not None and foreground and self.foreground
                and 0 <= elapsed <= self.MAX_SAMPLE_GAP):
            if self.playing and playing:
                added = elapsed
            else:
                added = max(0.0, min(now, self.last_activity + self.IDLE_SECONDS) - self.last_sample)
            self.document.active_work_seconds += added
        # Poll gaps may mean sleep/suspend or a blocked GUI. Never charge that gap.
        if elapsed > self.MAX_SAMPLE_GAP or not foreground:
            self.last_activity = float("-inf")
        if foreground and (activity or playing):
            self.last_activity = now
        self.last_sample = now
        self.foreground = foreground
        self.playing = playing
        return added
