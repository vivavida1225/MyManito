importScripts("https://www.gstatic.com/firebasejs/11.10.0/firebase-app-compat.js");
importScripts("https://www.gstatic.com/firebasejs/11.10.0/firebase-messaging-compat.js");

firebase.initializeApp({
  apiKey: "AIzaSyCOsNcMvmrNsTlFK2mqkQzF7TdY_dVRwAI",
  authDomain: "mymanito-alert.firebaseapp.com",
  projectId: "mymanito-alert",
  storageBucket: "mymanito-alert.firebasestorage.app",
  messagingSenderId: "525194715167",
  appId: "1:525194715167:web:a5ccabeb61934a6aaeb52a",
});

const messaging = firebase.messaging();
