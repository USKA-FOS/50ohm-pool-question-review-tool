(() => {
  const allowed = new Set([
    "question", "answer_a", "answer_b", "answer_c", "answer_d",
    "metadata_class_level", "metadata_rationale", "metadata_motivation",
    "picture_question_url", "picture_answer_a_url", "picture_answer_b_url",
    "picture_answer_c_url", "picture_answer_d_url", "comment",
  ]);

  function start() {
    const expired = document.getElementById("expired-draft");
    if (expired) {
      try {
        const draft = JSON.parse(expired.textContent);
        sessionStorage.setItem(draft.storage_key, JSON.stringify(draft.fields));
        document.getElementById("draft-status").textContent =
          "Your inputs are saved in this tab. After signing in, reopen the same question with the same languages to restore them. A copyable backup is also shown below.";
      } catch (error) {
        document.getElementById("draft-status").textContent =
          "Browser storage is unavailable. Copy the backup below before reconnecting.";
      }
      return;
    }

    const form = document.getElementById("review-form");
    if (!form) return;
    const key = "50ohm-review-draft:" + JSON.stringify([
      form.dataset.campaign, form.dataset.question,
      form.dataset.reference, form.dataset.review,
    ]);
    let fields;
    try {
      const saved = sessionStorage.getItem(key);
      if (!saved) return;
      fields = JSON.parse(saved);
      if (!fields || typeof fields !== "object" || Array.isArray(fields)) return;
    } catch (error) { return; }

    for (const [name, value] of Object.entries(fields)) {
      if (!allowed.has(name)) continue;
      if (name === "metadata_rationale" && Array.isArray(value)) {
        const list = document.getElementById("rationale-list");
        const add = document.getElementById("add-rationale");
        if (!list || !add || add.disabled || !value.every(item => typeof item === "string")) continue;
        list.replaceChildren();
        for (const text of value) {
          const row = document.createElement("div");
          row.className = "rationale-edit-row d-flex gap-2 mt-2";
          const area = document.createElement("textarea");
          area.name = name;
          area.className = "form-control auto-size-textarea";
          area.rows = 1;
          area.value = text;
          const remove = document.createElement("button");
          remove.type = "button";
          remove.className = "btn btn-outline-danger remove-rationale";
          remove.textContent = "Remove";
          row.append(area, remove);
          list.append(row);
        }
        continue;
      }
      if (typeof value !== "string") continue;
      for (const control of form.querySelectorAll('[name="' + name + '"]')) {
        if (control.disabled) continue;
        if (control.tagName === "SELECT" && !Array.from(control.options).some(option => option.value === value)) continue;
        control.value = value;
        control.dispatchEvent(new Event("input", { bubbles: true }));
        control.dispatchEvent(new Event("change", { bubbles: true }));
      }
    }

    const notice = document.createElement("section");
    notice.className = "alert alert-warning";
    notice.setAttribute("role", "status");
    const text = document.createElement("p");
    text.textContent = "Recovered inputs from an interrupted save. Check GitHub state before committing: a previous operation may already have completed. Disabled fields were not changed. Nothing was submitted automatically.";
    const details = document.createElement("details");
    const title = document.createElement("summary");
    title.textContent = "Recovered inputs (copyable backup)";
    const backup = document.createElement("textarea");
    backup.className = "form-control";
    backup.readOnly = true;
    backup.rows = 8;
    backup.value = JSON.stringify(fields, null, 2);
    details.append(title, backup);
    notice.append(text, details);
    form.insertAdjacentElement("beforebegin", notice);
    try { sessionStorage.removeItem(key); } catch (error) {}
  }
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", start);
  } else { start(); }
})();
