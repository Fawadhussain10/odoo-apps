/** @odoo-module **/

document.addEventListener('DOMContentLoaded', function () {
    "use strict";

    // Activate popover
    $(function () {
      $('[data-toggle="popover"]').popover({
        html: true,
        sanitize: false
      })
    })

    //close on focus
    $('.popover-dismiss').popover({
      trigger: 'focus'
    })

    $("#PbProcedureRecordSearch").on('keyup', function() {
        var input, filter, records, rec, i, txtValue;
        input = document.getElementById("PbProcedureRecordSearch");
        filter = input.value.toUpperCase();
        records = document.getElementsByClassName("pb_dental_procedure");
        for (i = 0; i < records.length; i++) {
            rec = records[i].getElementsByClassName("pb_procedure_label")[0];
            txtValue = rec.textContent || rec.innerText;
            if (txtValue.toUpperCase().indexOf(filter) > -1) {
                records[i].style.display = "";
            } else {
                records[i].style.display = "none";
            }
        }
    });

});
