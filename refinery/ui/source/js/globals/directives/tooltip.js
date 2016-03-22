'use strict';

var TooltipCtrl = function ($element) {
  var _element = $element;

  // This is the actual controller, which still has access to `_element` but
  // `_element` is hidden from the public
  var tooltip = function () {
    _element
      .attr('data-container', this.container)
      .one('mouseenter', function () {
        // Initialize the tool tip plugin when the element is hovered the
        // first time by the mouse cursor. This ensures that Angular has
        // successfully rendered the title and avoids performance issues.
        _element.tooltip({
          placement: this.placement
        });
        // After initializing the plugin we need to trigger the `mouseover`
        // event again to immediately show the tool tip.
        _element.trigger('mouseenter', _element);
      }.bind(this));
  };

  return tooltip.apply(this);
};

var tooltipDirective = function () {
  return {
    bindToController: {
      container: '@refineryTooltipContainer',
      placement: '@refineryTooltipPlacement'
    },
    controller: 'TooltipCtrl',
    controllerAs: 'tooltip',
    restrict: 'A'
  };
};

angular
  .module('tooltip', [])
  .controller('TooltipCtrl', ['$element', TooltipCtrl])
  .directive('refineryTooltip', [tooltipDirective]);
