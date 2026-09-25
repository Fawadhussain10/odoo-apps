/* global Popover */

function pbDentalChartInit() {
    // Activate popovers (Bootstrap 5, jQuery-free)
    for (const el of document.querySelectorAll('[data-toggle="popover"]')) {
        new Popover(el, { html: true, sanitize: false });
    }
    // close on focus
    for (const el of document.querySelectorAll(".popover-dismiss")) {
        new Popover(el, { trigger: "focus" });
    }

    const input = document.getElementById("PbProcedureRecordSearch");
    if (input) {
        input.addEventListener("keyup", () => {
            const filter = input.value.toUpperCase();
            for (const record of document.getElementsByClassName("pb_dental_procedure")) {
                const label = record.getElementsByClassName("pb_procedure_label")[0];
                const txtValue = label.textContent || label.innerText;
                record.style.display = txtValue.toUpperCase().indexOf(filter) > -1 ? "" : "none";
            }
        });
    }
}

if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", pbDentalChartInit);
} else {
    pbDentalChartInit();
}
