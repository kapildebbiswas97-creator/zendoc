(function () {
  "use strict";
  const button = document.getElementById("razorpay-checkout");
  const form = document.getElementById("razorpay-verify-form");
  if (!button || !form || typeof window.Razorpay !== "function") return;

  button.addEventListener("click", function () {
    const options = {
      key: button.dataset.key,
      amount: Number(button.dataset.amount),
      currency: button.dataset.currency || "INR",
      name: button.dataset.name || "ZENDOC",
      description: button.dataset.description || "Connected care payment",
      order_id: button.dataset.orderId,
      handler: function (response) {
        document.getElementById("razorpay-payment-id").value = response.razorpay_payment_id || "";
        document.getElementById("razorpay-order-id").value = response.razorpay_order_id || "";
        document.getElementById("razorpay-signature").value = response.razorpay_signature || "";
        form.submit();
      },
      theme: { color: "#0b6b61" }
    };
    const checkout = new window.Razorpay(options);
    checkout.open();
  });
})();
