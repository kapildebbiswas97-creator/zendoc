(() => {
  const toggle = document.getElementById("show-password-toggle");
  const password = document.getElementById("password-field");
  if (!toggle || !password) return;
  toggle.addEventListener("change", () => {
    password.type = toggle.checked ? "text" : "password";
  });
})();
