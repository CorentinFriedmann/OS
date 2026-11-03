// ╔══════════════════════════════════════════════════════════════╗
// ║  NOVA OS — écran de connexion « verre » (thème SDDM, Qt 6)    ║
// ╚══════════════════════════════════════════════════════════════╝
import QtQuick 2.15
import QtQuick.Controls 2.15

Rectangle {
    id: root
    width: 1920
    height: 1080
    color: "#0b0d12"

    // Palette « Verre » (branding/palette.json)
    readonly property color accent: "#8ab4ff"
    readonly property color danger: "#ff8f8f"
    readonly property color fg: "#eef1f6"
    readonly property color dim: "#a4adbd"
    readonly property color muted: "#6c7486"
    readonly property var frLocale: Qt.locale("fr_FR")
    property int sessionIndex: sessionModel.lastIndex >= 0 ? sessionModel.lastIndex : 0

    function doLogin() {
        message.text = ""
        busy.running = true
        sddm.login(userField.text, passwordField.text, root.sessionIndex)
    }

    Connections {
        target: sddm
        function onLoginFailed() {
            busy.running = false
            message.text = "Mot de passe incorrect"
            passwordField.text = ""
            passwordField.forceActiveFocus()
            shake.start()
        }
        function onLoginSucceeded() { message.text = "" }
    }

    // --- fond : lumière douce + voile sombre -------------------------------------------
    Image {
        anchors.fill: parent
        source: config.background || "background.jpg"
        fillMode: Image.PreserveAspectCrop
        asynchronous: true
        smooth: true
    }
    Rectangle {
        anchors.fill: parent
        gradient: Gradient {
            GradientStop { position: 0.0; color: "#660b0d12" }
            GradientStop { position: 0.6; color: "#330b0d12" }
            GradientStop { position: 1.0; color: "#990b0d12" }
        }
    }

    // --- heure et date ------------------------------------------------------------------
    Column {
        anchors.horizontalCenter: parent.horizontalCenter
        y: parent.height * 0.10
        spacing: 6
        Text {
            id: clock
            anchors.horizontalCenter: parent.horizontalCenter
            font.family: "Inter"
            font.pixelSize: Math.round(root.height * 0.10)
            font.weight: Font.Light
            color: root.fg
            text: Qt.formatTime(new Date(), "HH:mm")
        }
        Text {
            id: date
            anchors.horizontalCenter: parent.horizontalCenter
            font.family: "Inter"
            font.pixelSize: Math.round(root.height * 0.022)
            font.weight: Font.Medium
            color: root.dim
            text: root.frLocale.toString(new Date(), "dddd d MMMM")
        }
    }
    Timer {
        interval: 1000
        running: true
        repeat: true
        onTriggered: {
            clock.text = Qt.formatTime(new Date(), "HH:mm")
            date.text = root.frLocale.toString(new Date(), "dddd d MMMM")
        }
    }

    // --- carte de connexion --------------------------------------------------------------
    Rectangle {
        id: card
        width: 440
        height: form.implicitHeight + 64
        anchors.centerIn: parent
        anchors.verticalCenterOffset: root.height * 0.08
        radius: 26
        color: "#b8141820"
        border.color: "#1fffffff"
        border.width: 1

        SequentialAnimation {
            id: shake
            NumberAnimation { target: card; property: "anchors.horizontalCenterOffset"; to: -14; duration: 50 }
            NumberAnimation { target: card; property: "anchors.horizontalCenterOffset"; to: 14; duration: 70 }
            NumberAnimation { target: card; property: "anchors.horizontalCenterOffset"; to: -8; duration: 60 }
            NumberAnimation { target: card; property: "anchors.horizontalCenterOffset"; to: 0; duration: 60 }
        }

        Column {
            id: form
            anchors.centerIn: parent
            width: parent.width - 64
            spacing: 16

            Image {
                source: "logo.png"
                width: 76
                height: 76
                anchors.horizontalCenter: parent.horizontalCenter
                smooth: true
            }
            Text {
                anchors.horizontalCenter: parent.horizontalCenter
                text: "Nova OS"
                font.family: "Inter"
                font.pixelSize: 24
                font.weight: Font.DemiBold
                color: root.fg
            }

            TextField {
                id: userField
                width: parent.width
                height: 50
                text: userModel.lastUser
                placeholderText: "Nom d'utilisateur"
                font.family: "Inter"
                font.pixelSize: 16
                color: root.fg
                placeholderTextColor: root.muted
                leftPadding: 18
                background: Rectangle {
                    radius: 14
                    color: "#0dffffff"
                    border.width: 1
                    border.color: userField.activeFocus ? root.accent : "#1fffffff"
                }
                KeyNavigation.tab: passwordField
                onAccepted: passwordField.forceActiveFocus()
            }

            TextField {
                id: passwordField
                width: parent.width
                height: 50
                echoMode: TextInput.Password
                passwordCharacter: "●"
                placeholderText: "Mot de passe"
                font.family: "Inter"
                font.pixelSize: 16
                color: root.fg
                placeholderTextColor: root.muted
                leftPadding: 18
                focus: true
                background: Rectangle {
                    radius: 14
                    color: "#0dffffff"
                    border.width: 1
                    border.color: passwordField.activeFocus ? root.accent : "#1fffffff"
                }
                KeyNavigation.tab: loginButton
                onAccepted: root.doLogin()
            }

            Button {
                id: loginButton
                width: parent.width
                height: 50
                onClicked: root.doLogin()
                contentItem: Text {
                    text: busy.running ? "Connexion…" : "Se connecter"
                    font.family: "Inter"
                    font.pixelSize: 15
                    font.weight: Font.DemiBold
                    color: "#0b0d12"
                    horizontalAlignment: Text.AlignHCenter
                    verticalAlignment: Text.AlignVCenter
                }
                background: Rectangle {
                    radius: 14
                    color: loginButton.down ? "#6f9dfa" : (loginButton.hovered ? "#a9c7ff" : root.accent)
                }
            }

            Text {
                id: message
                width: parent.width
                horizontalAlignment: Text.AlignHCenter
                font.family: "Inter"
                font.pixelSize: 14
                color: root.danger
                text: ""
                visible: text.length > 0
            }

            Timer { id: busy; interval: 15000; onTriggered: running = false }
        }
    }

    // --- barre du bas : session et alimentation -------------------------------------------
    Row {
        anchors.left: parent.left
        anchors.bottom: parent.bottom
        anchors.margins: 32
        spacing: 10
        Text {
            anchors.verticalCenter: parent.verticalCenter
            text: "Session"
            font.family: "Inter"
            font.pixelSize: 14
            color: root.dim
        }
        ComboBox {
            id: sessionBox
            width: 220
            height: 40
            model: sessionModel
            textRole: "name"
            currentIndex: root.sessionIndex
            onActivated: root.sessionIndex = currentIndex
            font.family: "Inter"
            contentItem: Text {
                leftPadding: 14
                text: sessionBox.displayText
                font.family: "Inter"
                font.pixelSize: 14
                color: root.fg
                verticalAlignment: Text.AlignVCenter
                elide: Text.ElideRight
            }
            background: Rectangle { radius: 12; color: "#b8141820"; border.color: "#1fffffff"; border.width: 1 }
        }
    }

    Row {
        anchors.right: parent.right
        anchors.bottom: parent.bottom
        anchors.margins: 32
        spacing: 10
        Repeater {
            model: [
                { label: "Veille", action: "suspend", enabled: sddm.canSuspend },
                { label: "Redémarrer", action: "reboot", enabled: sddm.canReboot },
                { label: "Éteindre", action: "poweroff", enabled: sddm.canPowerOff }
            ]
            delegate: Button {
                visible: modelData.enabled
                height: 40
                onClicked: {
                    if (modelData.action === "suspend") sddm.suspend()
                    else if (modelData.action === "reboot") sddm.reboot()
                    else sddm.powerOff()
                }
                contentItem: Text {
                    leftPadding: 16
                    rightPadding: 16
                    text: modelData.label
                    font.family: "Inter"
                    font.pixelSize: 14
                    color: modelData.action === "poweroff" ? root.danger : root.fg
                    verticalAlignment: Text.AlignVCenter
                }
                background: Rectangle {
                    radius: 12
                    color: parent.hovered ? "#24ffffff" : "#b8141820"
                    border.color: "#1fffffff"
                    border.width: 1
                }
            }
        }
    }

    Component.onCompleted: {
        if (userField.text.length > 0) passwordField.forceActiveFocus()
        else userField.forceActiveFocus()
    }
}
