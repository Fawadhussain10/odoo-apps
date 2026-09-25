/* global Chart */

function pbPortalChartInit() {
    const input = document.querySelector("input[name='patient_portal_line_graph']");
    const canvas = document.getElementById("PBPatientLineChart");
    if (!input || !input.value || !canvas) {
        return;
    }
    new Chart(canvas, {
        type: "line",
        data: JSON.parse(input.value),
        options: {
            scales: {
                x: {
                    ticks: {
                        autoSkip: false,
                        maxRotation: 45,
                        minRotation: 45,
                    },
                },
            },
        },
    });
}

if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", pbPortalChartInit);
} else {
    pbPortalChartInit();
}
