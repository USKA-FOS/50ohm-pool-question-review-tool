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

    @property
    def n_reviewed(self):
        # FIXME: Only makes sense to call on subsection node
        return sum([c.reviewed for c in self.children])

    @property
    def progress(self):
        # FIXME: Only makes sense to call on subsection node
        return 100*self.n_reviewed/len(self.children)

class toc:
    def __init__(self):
        # FIXME: Find a better way to compile TOC. This is not the JSON file we should use
        input_json = json.loads(Path('fragenkatalog3b.json').read_text().replace('\\u00df', 'ss'))
        self.toc = tree_node(parent=None, value='')
        self.question_map = {} # Use to look up chapters based on question key

        internal_nodes = [] # FIXME: Only needed for pruning below
        for chapter in input_json['sections']:
            current_chapter = tree_node(parent=toc, value=chapter['title'])
            internal_nodes.append(current_chapter)
            self.toc.children.append(current_chapter)
            for section in chapter['sections']:
                current_section = tree_node(parent=current_chapter, value=section['title'])
                internal_nodes.append(current_section)
                current_chapter.children.append(current_section)
                for subsection in section['sections']:
                    current_subsection = tree_node(parent=current_section, value=subsection['title'])
                    internal_nodes.append(current_subsection)
                    current_section.children.append(current_subsection)
                    for q in reversed(subsection['questions']):
                        current_question = tree_node(parent=current_subsection, value=q['number'])

                        # FIXME: Only needed for pruning below
                        test = q['number'].startswith('NA') or q['number'].startswith('NB') or q['number'].startswith('AF')
                        if not test: continue

                        current_subsection.children.append(current_question)
                        self.question_map[q['number']] = current_question
            break # FIXME: skip B & V

        # Here we do the pruning
        for q in self.question_map.values():
            q.parent.painted = True
            q.parent.parent.painted = True
            q.parent.parent.parent.painted = True
            q.parent.parent.parent.parent.painted = True

        for n in internal_nodes:
            if not n.painted:
                n.parent.children.remove(n)


    def lookup(self, q: str):
        subsection = self.question_map[q].parent
        section = subsection.parent
        chapter = section.parent
        return chapter.value, section.value, subsection.value

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
        q_node = self.question_map[q]
        subsection = q_node.parent
        section = subsection.parent
        idx = section.children.index(subsection)
        if idx+1 == len(section.children):
            return None
        return section.children[idx+1].children[0].value

    def prev_q_in_section(self, q: str):
        q_node = self.question_map[q]
        subsection = q_node.parent
        section = subsection.parent
        idx = section.children.index(subsection)
        if idx == 0:
            return None
        return section.children[idx-1].children[0].value

    def mark_reviewed(self, q: str):
        self.question_map[q].reviewed = True
