import json
from pathlib import Path
from dataclasses import dataclass, field

@dataclass
class tree_node:
    parent: "tree_node" or None
    value: str
    children: list["tree_node"] = field(default_factory=list)
    painted: bool = False # FIXME: Only needed for pruning below
    reviewed: bool = False
    is_question: bool = False

    @property
    def is_review_group(self):
        return bool(self.children) and all(child.is_question for child in self.children)

    @property
    def question_count(self):
        if self.is_question:
            return 1
        return sum(child.question_count for child in self.children)

    @property
    def n_reviewed(self):
        if self.is_question:
            return int(self.reviewed)
        return sum(child.n_reviewed for child in self.children)

    @property
    def progress(self):
        return 100 * self.n_reviewed / self.question_count if self.question_count else 0

    @property
    def first_question(self):
        if self.is_question:
            return self.value
        for child in self.children:
            first = child.first_question
            if first is not None:
                return first
        return None

class toc:
    def __init__(self, input_json=None):
        if input_json is None:
            input_json = json.loads(Path('fragenkatalog3b.json').read_text())
        self.toc = tree_node(parent=None, value='')
        self.question_map = {} # Use to look up chapters based on question key
        self.review_groups = []
        self.subsections = self.review_groups

        def add_group(source, parent):
            current = tree_node(parent=parent, value=source['title'])
            parent.children.append(current)
            if 'questions' in source:
                self.review_groups.append(current)
                for question in source['questions']:
                    question_node = tree_node(
                        parent=current,
                        value=question['number'],
                        is_question=True,
                    )
                    current.children.append(question_node)
                    self.question_map[question['number']] = question_node
            else:
                for child in source['sections']:
                    add_group(child, current)

        for chapter in input_json['sections']:
            add_group(chapter, self.toc)


    def lookup(self, q: str):
        values = []
        current = self.question_map[q].parent
        while current is not None and current.parent is not None:
            values.append(current.value)
            current = current.parent
        return tuple(reversed(values))

    def next_q_in_subsection(self, q: str):
        q_node = self.question_map[q]
        subsection = q_node.parent
        idx = subsection.children.index(q_node)
        if idx+1 == len(subsection.children):
            return None
        return subsection.children[idx+1].value

    def prev_q_in_subsection(self, q: str):
        q_node = self.question_map[q]
        subsection = q_node.parent
        idx = subsection.children.index(q_node)
        if idx == 0:
            return None
        return subsection.children[idx-1].value

    def next_q_in_section(self, q: str):
        group = self.question_map[q].parent
        idx = self.review_groups.index(group)
        if idx+1 == len(self.review_groups):
            return None
        return self.review_groups[idx+1].first_question

    def prev_q_in_section(self, q: str):
        group = self.question_map[q].parent
        idx = self.review_groups.index(group)
        if idx == 0:
            return None
        return self.review_groups[idx-1].first_question

    def mark_reviewed(self, q: str):
        self.question_map[q].reviewed = True
