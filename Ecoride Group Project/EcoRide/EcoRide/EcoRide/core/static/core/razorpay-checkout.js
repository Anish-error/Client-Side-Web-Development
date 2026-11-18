document.addEventListener("DOMContentLoaded", () => {
  const optionsElement = document.getElementById("razorpay-options");
  const verifyForm = document.getElementById("razorpay-verify-form");
  const openButton = document.getElementById("open-checkout");
  const status = document.getElementById("checkout-status");
  if (!optionsElement || !verifyForm || !openButton) return;

  const options = JSON.parse(optionsElement.textContent || "{}");
  openButton.addEventListener("click", () => {
    if (!window.Razorpay) {
      status.textContent =
        "Secure checkout did not load. Check your connection and try again.";
      return;
    }
    const checkout = new window.Razorpay({
      ...options,
      handler: (response) => {
        verifyForm.elements.razorpay_payment_id.value =
          response.razorpay_payment_id;
        verifyForm.elements.razorpay_signature.value =
          response.razorpay_signature;
        verifyForm.requestSubmit();
      },
      modal: {
        ondismiss: () => {
          status.textContent =
            "Checkout closed. Your bicycle remains reserved until you cancel this reservation.";
        },
      },
    });
    checkout.on("payment.failed", (response) => {
      status.textContent =
        response.error?.description || "Payment failed. Please try again.";
    });
    checkout.open();
  });
});
