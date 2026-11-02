// ╔══════════════════════════════════════════════════════════════╗
// ║  NOVA OS — écran de connexion néon (thème SDDM, Qt 6)         ║
// ╚══════════════════════════════════════════════════════════════╝
import QtQuick 2.15
import QtQuick.Controls 2.15

Rectangle {
    id: root
    width: 1920
    height: 1080
    color: "#05060d"

    readonly property color cyan: "#00f0ff"
    readonly property color magenta: "#ff2bd6"
    readonly property color violet: "#8a5cff"
    readonly property color fg: "#e6f1ff"
    readonly property color dim: "#8b95b8"
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

    // --- fond : ville néon + voile sombre -------------------------------------------
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
            GradientStop { position: 0.0; color: "#8805060d" }
            GradientStop { position: 0.6; color: "#5505060d" }
            GradientStop { position: 1.0; color: "#dd05060d" }
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
            font.family: "Orbitron"
            font.pixelSize: Math.round(root.height * 0.09)
            font.weight: Font.Black
            color: root.fg
            style: Text.Outline
            styleColor: "#3300f0ff"
            text: Qt.formatTime(new Date(), "HH:mm")
        }
        Text {
            id: date
            anchors.horizontalCenter: parent.horizontalCenter
            font.family: "Orbitron"
            font.pixelSize: Math.round(root.height * 0.022)
            color: root.magenta
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
        color: "#d90a0d1a"
        border.color: "#6600f0ff"
        border.width: 1

        // halo néon autour de la carte
        Rectangle {
            anchors.fill: parent
            anchors.margins: -6
            z: -1
            radius: parent.radius + 6
            color: "transparent"
            border.color: "#2200f0ff"
            border.width: 6
        }

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
                text: "NOVA OS"
                font.family: "Orbitron"
                font.pixelSize: 22
                font.letterSpacing: 6
                font.weight: Font.Black
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
                placeholderTextColor: "#4a5378"
                leftPadding: 18
                background: Rectangle {
                    radius: 14
                    color: "#0dffffff"
                    border.width: userField.activeFocus ? 2 : 1
                    border.color: userField.activeFocus ? root.cyan : "#4d8a5cff"
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
                placeholderTextColor: "#4a5378"
                leftPadding: 18
                focus: true
                background: Rectangle {
                    radius: 14
                    color: "#0dffffff"
                    border.width: passwordField.activeFocus ? 2 : 1
                    border.color: passwordField.activeFocus ? root.cyan : "#4d8a5cff"
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
                    font.family: "Orbitron"
                    font.pixelSize: 15
                    font.weight: Font.Bold
                    color: "#05060d"
                    horizontalAlignment: Text.AlignHCenter
                    verticalAlignment: Text.AlignVCenter
                }
                background: Rectangle {
                    radius: 14
                    gradient: Gradient {
                        orientation: Gradient.Horizontal
                        GradientStop { position: 0.0; color: loginButton.down ? "#00b8c4" : root.cyan }
                        GradientStop { position: 1.0; color: loginButton.down ? "#6a44cc" : root.violet }
                    }
                }
            }

            Text {
                id: message
                width: parent.width
                horizontalAlignment: Text.AlignHCenter
                font.family: "Inter"
                font.pixelSize: 14
                color: "#ff3860"
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
            background: Rectangle { radius: 12; color: "#cc0a0d1a"; border.color: "#4d8a5cff"; border.width: 1 }
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
                    color: modelData.action === "poweroff" ? root.magenta : root.fg
                    verticalAlignment: Text.AlignVCenter
                }
                background: Rectangle {
                    radius: 12
                    color: parent.hovered ? "#2600f0ff" : "#cc0a0d1a"
                    border.color: modelData.action === "poweroff" ? "#66ff2bd6" : "#4d8a5cff"
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
