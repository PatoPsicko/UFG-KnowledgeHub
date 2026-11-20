import 'package:flutter_test/flutter_test.dart';
import 'package:ufg_hub/widgets/common.dart';

void main() {
  test('fileSize formatea bytes', () {
    expect(fileSize(512), '512 B');
    expect(fileSize(2048), '2 KB');
  });
}
