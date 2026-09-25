document.addEventListener("DOMContentLoaded", function () {

    var inputValue = function (name) {
        var input = document.querySelector("input[name='" + name + "']");
        return input ? input.value : "";
    };
    var Domain = inputValue("server_name");
    var MeetingName = inputValue("meeting_name");
    var MeetingPwd = inputValue("meeting_pwd");
    var ReturnUrl = inputValue("site_url");
    

    var domain = Domain;
    var options = {
        roomName: MeetingName,
        parentNode: document.getElementById('pb_videocall'),
        configOverwrite: {
            disableDeepLinking: true
        },
        interfaceConfigOverwrite: {
            SHOW_JITSI_WATERMARK: false,
            SHOW_WATERMARK_FOR_GUESTS: false,
        }
    }
    var api = new JitsiMeetExternalAPI(domain, options);
    
    if (MeetingPwd) {
        api.addEventListener('videoConferenceJoined' , function(event) {
            if (event.role === "moderator") {
                api.executeCommand('password', MeetingPwd);
            }
        });

        api.addEventListener('participantRoleChanged', function(event) {
            if (event.role === "moderator") {
                api.executeCommand('password', MeetingPwd);
            }
        });
        //setTimeout(function () {
        //}, 20000);
    }
    api.addEventListener('readyToClose' , function() {
        window.location.href = ReturnUrl;
    });
});