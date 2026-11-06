from dataclasses import dataclass, field


@dataclass
class Project:
    id: int
    name: str
    owner: str
    tags: set = field(default_factory=set)
    updated: int = 0


class Store:
    def __init__(self):
        self.projects = {}
        self.next_id = 1
        self.clock = 0

    def tick(self):
        self.clock += 1
        return self.clock
