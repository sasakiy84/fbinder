// Progressive enhancement for generated pages.
(() => {
  const copyButtons = document.querySelectorAll("[data-copy-content]");

  const copyText = async (text) => {
    if (navigator.clipboard && window.isSecureContext) {
      await navigator.clipboard.writeText(text);
      return;
    }

    const textarea = document.createElement("textarea");
    textarea.value = text;
    textarea.setAttribute("readonly", "");
    textarea.style.position = "fixed";
    textarea.style.inset = "0 auto auto 0";
    textarea.style.opacity = "0";
    document.body.append(textarea);
    textarea.select();
    const copied = document.execCommand("copy");
    textarea.remove();

    if (!copied) {
      throw new Error("copy command failed");
    }
  };

  for (const button of copyButtons) {
    button.addEventListener("click", async () => {
      const targetId = button.getAttribute("data-copy-content");
      const statusId = button.getAttribute("aria-describedby");
      const target = targetId ? document.getElementById(targetId) : null;
      const status = statusId ? document.getElementById(statusId) : null;
      const text = target instanceof HTMLTextAreaElement || target instanceof HTMLInputElement
        ? target.value
        : target ? target.innerText : "";

      if (!text.trim()) {
        if (status) {
          status.textContent = "コピーするMarkdownがありません";
        }
        return;
      }

      try {
        await copyText(text);
        const label = button.getAttribute("data-copy-label") || "Markdownをコピー";
        button.textContent = "コピー済み";
        if (status) {
          status.textContent = "Markdownをコピーしました";
        }
        window.setTimeout(() => {
          button.textContent = label;
          if (status) {
            status.textContent = "";
          }
        }, 1800);
      } catch {
        if (status) {
          status.textContent = "コピーできませんでした";
        }
      }
    });
  }
})();
