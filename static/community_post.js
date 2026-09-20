(() => {
  const button = document.getElementById("share-community-post");
  const status = document.getElementById("share-community-status");
  if (!button) return;

  const setStatus = value => {
    if (status) status.textContent = value;
  };

  button.addEventListener("click", async () => {
    const payload = {
      title: button.dataset.shareTitle || "ZENDOC Health Community",
      url: window.location.href
    };
    try {
      if (navigator.share) {
        await navigator.share(payload);
        setStatus("Share sheet opened.");
        return;
      }
      if (navigator.clipboard && navigator.clipboard.writeText) {
        await navigator.clipboard.writeText(window.location.href);
        setStatus("Post link copied.");
        return;
      }
      setStatus("Copy this page address from your browser to share the post.");
    } catch (error) {
      if (error && error.name === "AbortError") {
        setStatus("Share cancelled.");
      } else {
        setStatus("Could not copy automatically. Copy this page address from your browser.");
      }
    }
  });
})();
