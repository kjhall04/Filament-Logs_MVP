(function () {
    if (window.bootstrap) {
        return;
    }

    document.querySelectorAll("[data-bs-toggle='collapse']").forEach(function (toggle) {
        toggle.addEventListener("click", function () {
            var selector = toggle.getAttribute("data-bs-target");
            if (!selector) {
                return;
            }

            var target = document.querySelector(selector);
            if (!target) {
                return;
            }

            var isOpen = target.classList.toggle("show");
            toggle.setAttribute("aria-expanded", isOpen ? "true" : "false");
        });
    });

    document.addEventListener("click", function (event) {
        var dismissButton = event.target.closest("[data-bs-dismiss='alert']");
        if (!dismissButton) {
            return;
        }

        var alert = dismissButton.closest(".alert");
        if (!alert) {
            return;
        }

        alert.classList.remove("show");
        window.setTimeout(function () {
            if (alert.parentNode) {
                alert.parentNode.removeChild(alert);
            }
        }, 150);
    });
})();
