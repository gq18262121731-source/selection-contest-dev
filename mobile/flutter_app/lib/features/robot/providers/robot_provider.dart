import 'package:flutter/foundation.dart';

import '../models/robot_status.dart';

class RobotProvider extends ChangeNotifier {
  RobotStatus _status = RobotStatus.demo();

  RobotStatus get status => _status;

  void setMode(RobotMode mode) {
    if (_status.mode == mode) {
      return;
    }
    _status = RobotStatus.demo(mode: mode, robotId: _status.robotId);
    notifyListeners();
  }

  void applyRemoteStatus(RobotStatus status) {
    _status = status;
    notifyListeners();
  }
}
