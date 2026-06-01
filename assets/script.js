const copyButton = document.querySelector("[data-copy]");

if (copyButton) {
  copyButton.addEventListener("click", async () => {
    const target = document.querySelector(copyButton.dataset.copy);
    if (!target) return;

    const original = copyButton.textContent;
    try {
      await navigator.clipboard.writeText(target.textContent.trim());
      copyButton.textContent = "Copied";
      copyButton.classList.add("copied");
      setTimeout(() => {
        copyButton.textContent = original;
        copyButton.classList.remove("copied");
      }, 1600);
    } catch {
      copyButton.textContent = "Select BibTeX";
      setTimeout(() => {
        copyButton.textContent = original;
      }, 1600);
    }
  });
}
