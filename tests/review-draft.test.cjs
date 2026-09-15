const test = require("node:test");
const assert = require("node:assert/strict");
const vm = require("node:vm");
const fs = require("node:fs");
const script = fs.readFileSync("static/review-draft.js", "utf8");
const key = '50ohm-review-draft:["default","NF101","de","fr"]';

function storage() {
  const values = new Map();
  return { values,
    getItem(k) { return values.get(k) || null; },
    setItem(k, v) { values.set(k, v); },
    removeItem(k) { values.delete(k); },
  };
}
function element() {
  return { children: [], append(...v) { this.children.push(...v); },
    setAttribute() {}, insertAdjacentElement(where, notice) { this.notice = notice; },
    dispatchEvent() {}, value: "", disabled: false };
}

test("expired save stores only its scoped fields", () => {
  const store = storage();
  const status = {};
  vm.runInNewContext(script, {
    document: { readyState: "complete", getElementById(id) {
      return id === "expired-draft" ? { textContent: JSON.stringify({ storage_key: key, fields: { question: "text" } }) } : status;
    } }, sessionStorage: store,
  });
  assert.deepEqual(JSON.parse(store.values.get(key)), { question: "text" });
  assert.match(status.textContent, /saved in this tab/);
});

test("blocked browser storage gives copy-before-login message", () => {
  const status = {};
  vm.runInNewContext(script, {
    document: { readyState: "complete", getElementById(id) {
      return id === "expired-draft" ? { textContent: JSON.stringify({ storage_key: key, fields: {} }) } : status;
    } }, sessionStorage: { setItem() { throw Error("blocked"); } },
  });
  assert.match(status.textContent, /Copy the backup/);
});

test("restoration respects disabled fields and fresh SHA and never submits", () => {
  const store = storage();
  store.setItem(key, JSON.stringify({ question: "restored", answer_a: "old answer", sha: "obsolete", action: "commit" }));
  const form = element();
  form.dataset = { campaign: "default", question: "NF101", reference: "de", review: "fr" };
  form.submit = () => { throw Error("automatic write forbidden"); };
  const question = element();
  const answer = element(); answer.disabled = true;
  const sha = element(); sha.value = "fresh-sha";
  form.querySelectorAll = selector => selector.includes("question") ? [question] : selector.includes("answer_a") ? [answer] : [sha];
  vm.runInNewContext(script, {
    document: { readyState: "complete", getElementById(id) { return id === "review-form" ? form : null; }, createElement: element },
    sessionStorage: store, Event: class {},
  });
  assert.equal(question.value, "restored");
  assert.equal(answer.value, "");
  assert.equal(sha.value, "fresh-sha");
  assert.match(form.notice.children[0].textContent, /Nothing was submitted automatically/);
  assert.equal(store.getItem(key), null);
});

test("another question or language does not consume draft", () => {
  const store = storage();
  store.setItem(key, JSON.stringify({ question: "text" }));
  const form = element();
  form.dataset = { campaign: "default", question: "OTHER", reference: "de", review: "fr" };
  vm.runInNewContext(script, {
    document: { readyState: "complete", getElementById(id) { return id === "review-form" ? form : null; } },
    sessionStorage: store,
  });
  assert.ok(store.getItem(key));
  assert.equal(form.notice, undefined);
});

test("repeated rationales are restored as plain textarea values", () => {
  const store = storage();
  store.setItem(key, JSON.stringify({ metadata_rationale: ["first reason", "<script>plain text</script>"] }));
  const form = element();
  form.dataset = { campaign: "default", question: "NF101", reference: "de", review: "fr" };
  const list = element();
  list.replaceChildren = () => { list.children = []; };
  const add = element();
  vm.runInNewContext(script, {
    document: { readyState: "complete", getElementById(id) {
      return id === "review-form" ? form : id === "rationale-list" ? list : id === "add-rationale" ? add : null;
    }, createElement: element },
    sessionStorage: store,
  });
  assert.equal(list.children.length, 2);
  assert.equal(list.children[0].children[0].value, "first reason");
  assert.equal(list.children[1].children[0].value, "<script>plain text</script>");
  assert.equal(list.children[0].children[1].type, "button");
});
