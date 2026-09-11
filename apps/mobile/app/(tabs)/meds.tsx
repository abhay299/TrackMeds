import { StyleSheet, View } from 'react-native';
import { Text } from 'react-native-paper';

export default function Meds() {
  return (
    <View style={styles.center}>
      <Text variant="bodyLarge">Medications arrive in Phase 1.</Text>
    </View>
  );
}

const styles = StyleSheet.create({ center: { flex: 1, alignItems: 'center', justifyContent: 'center' } });
