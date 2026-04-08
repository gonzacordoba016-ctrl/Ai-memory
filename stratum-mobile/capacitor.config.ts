import { CapacitorConfig } from '@capacitor/cli';

const config: CapacitorConfig = {
  appId: 'com.stratum.hardware',
  appName: 'Stratum',
  webDir: 'www',

  server: {
    cleartext: true,
    androidScheme: 'http',
  },

  plugins: {
    PushNotifications: {
      presentationOptions: ['badge', 'sound', 'alert'],
    },
    Camera: {
      // La app pide permiso de cámara en el primer uso
    },
    LocalNotifications: {
      smallIcon: 'ic_stat_icon_config_sample',
      iconColor: '#a4ffb9',
    },
  },

  android: {
    backgroundColor: '#0e0e0e',
  },

  ios: {
    backgroundColor: '#0e0e0e',
    contentInset: 'automatic',
  },
};

export default config;
