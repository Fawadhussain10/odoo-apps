/* global tui, blackTheme */
document.addEventListener("DOMContentLoaded", function () {
    var inputValue = function (name) {
        var input = document.querySelector("input[name='" + name + "']");
        return input ? input.value : "";
    };
    var pb_doc_id = inputValue("pb_doc_id");
    var pb_home_action = inputValue("pb_home_action");

    // Image editor
    var imageEditor = new tui.ImageEditor("#tui-image-editor-container", {
        includeUI: {
            loadImage: {
                path: "/web/content/" + pb_doc_id,
                name: "Image",
            },
            theme: blackTheme, // or whiteTheme blackTheme
            initMenu: "filter",
            menuBarPosition: "bottom",
        },
        cssMaxWidth: 700,
        cssMaxHeight: 500,
        usageStatistics: false,
    });
    window.onresize = function () {
        imageEditor.ui.resizeEditor();
    };

    //replace Download image to save
    var downloadBtn = document.querySelector(".tui-image-editor-header-buttons .tui-image-editor-download-btn");
    if (downloadBtn) {
        downloadBtn.outerHTML = '<button class="tui-image-editor-save-btn" id="PBdoSaveFile">Save</button>';
    }
    var logo = document.querySelector(".tui-image-editor-header-logo");
    if (logo) {
        logo.outerHTML = "<a href='" + pb_home_action + "' id='PbReturnAction' class='ml16'><img src='/pb_hms_body_chart/static/src/js/home-icon.jpeg' width='45' height='auto'><i class='oi mr-1 oi-3x' data-icon='home'/></a>";
    }

    // LISTEN TO THE CLICK AND SEND TO THE SERVER
    var saveBtn = document.getElementById("PBdoSaveFile");
    if (saveBtn) {
        saveBtn.addEventListener("click", function (e) {
            e.preventDefault();
            // Sent as a raw form-encoded body: the controller reads the data
            // URL from the (single) posted key, as jQuery.ajax used to send it.
            fetch("/my/pb/image/" + pb_doc_id + "?csrf_token=" + encodeURIComponent(inputValue("csrf_token")), {
                method: "POST",
                headers: { "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8" },
                body: imageEditor.toDataURL(),
                cache: "no-store",
            }).then(function () {
                var link = document.getElementById("PbReturnAction");
                if (link) {
                    link.click();
                }
            });
        });
    }
});
