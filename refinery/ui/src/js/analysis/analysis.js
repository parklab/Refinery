angular.module('refineryAnalysis')

.controller('AnalysisCtrl', function(
    $scope, $rootScope, $http, $window, $log, $timeout, workflow, timeStamp) {
    "use strict";

  var vm = this;

  $scope.$onRootScope('nodeSetChangedEvent', function(event, currentNodeSet) {
    $scope.analysisConfig.nodeSetUuid = currentNodeSet.uuid;
    $scope.analysisConfig.nodeRelationshipUuid = null;
    $log.debug("new nodeset: " + $scope.analysisConfig.nodeSetUuid);
  });

  $scope.$onRootScope('nodeRelationshipChangedEvent', function(event, currentNodeRelationship) {
    if (!currentNodeRelationship) {
      $scope.analysisConfig.nodeRelationshipUuid = null;
      $log.debug("new noderel undefined");
    }
    else {
      $scope.analysisConfig.nodeRelationshipUuid = currentNodeRelationship.uuid;
      $log.debug("new noderel: " + $scope.analysisConfig.nodeRelationshipUuid);
    }
    $scope.analysisConfig.nodeSetUuid = null;
  });

});
