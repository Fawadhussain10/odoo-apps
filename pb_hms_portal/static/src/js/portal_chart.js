$(document).ready(function () {  
    var PatientPortalData = $("input[name='patient_portal_line_graph']").val();

    if (PatientPortalData){
        PBPatientChartData = JSON.parse(PatientPortalData);
        new Chart(document.getElementById("PBPatientLineChart"), {
            type: 'line',
            data: PBPatientChartData,
            options: {
              scales: {
                xAxes: [{
                    ticks: {
                        autoSkip: false,
                        maxRotation: 45,
                        minRotation: 45,
                    }
                }]
              }
            }
        });

    }
});