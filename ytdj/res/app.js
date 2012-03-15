(function($, undefined) {
  window.YTPL = {models: {}, collections: {}, views: {}};

  _(YTPL.models).extend({
    Song: Backbone.Model.extend({
    })
  });

  _(YTPL.collections).extend({
    Results: Backbone.Collection.extend({
      model: YTPL.models.Song
    }),
    Playlist: Backbone.Collection.extend({
      model: YTPL.models.Song,
      url: function() {
        return this.plName + '/add';
      }
    })
  });

  YTPL.views.Result = Backbone.View.extend({
    tagName: 'li',
    className: 'cf',
    events: {
      'click': 'addToPL'
    },
    template:
      '<img src="<%= thumbnail.url %>">' +
      '<h3 class="title"><%= title %></h3>' +
      '<span class="author"><%= author %></span>',
    render: function() {
      this.$el.html(_.template(this.template, this.model.toJSON()));
      return this;
    },
    addToPL: function(e) {
      playlist.create(this.model.toJSON());
      results.reset([]);
    }
  });

  YTPL.views.Search = Backbone.View.extend({
    el: '#search',
    events: {
      'change input': 'search'
    },
    initialize: function() {
      this.collection.on('reset', this.showResults, this);
    },
    search: function(e) {
      var $q = this.$(e.target);
      var promise = $.ajax({
        url: '/search',
        data: {
          q: $q.val()
        },
        dataType: 'json'
      });

      promise.done(_.bind(function(response) {
        this.collection.reset(response);
      }, this));
    },
    showResults: function(collection) {
      var $results = this.$('#results', this.$el).empty();
      if (collection.length > 0) {
        collection.each(function(model) {
          var view = new YTPL.views.Result({
            model: model
          });
          $results.append(view.render().el);
        }, this);
      } else {
        this.$('input', this.$el).val('');
      }
    }
  });

  YTPL.views.Song = Backbone.View.extend({
    tagName: 'li',
    className: 'cf',
    template:
      '<img src="<%= thumbnail.url %>">' +
      '<h3 class="title"><%= title %></h3>' +
      '<span class="author"><%= author %></span>',
    render: function() {
      this.$el.html(_.template(this.template, this.model.toJSON()));
      return this;
    }
  });

  YTPL.views.Playlist = Backbone.View.extend({
    el: '#playlist',
    initialize: function() {
      this.collection.on('add', this.addSong, this);
    },
    addSong: function(model) {
      if (this.collection.length == 1) {
        this.$el.empty();
      }
      var view = new YTPL.views.Song({
        model: model
      });
      this.$el.append(view.render().el);
    }
  });

  var results = new YTPL.collections.Results();
  var playlist = new YTPL.collections.Playlist();

  YTPL.Router = Backbone.Router.extend({
    routes: {
      '': 'index',
      ':plName': 'default'
    },
    index: function() {
      $.ajax({
        url: '/new',
        dataType: 'json',
        success: _.bind(function(response) {
          this.navigate(response.name, true);
        }, this)
      });
    },
    'default': function(plName) {
      new YTPL.views.Search({collection: results});
      playlist.plName = plName;
      new YTPL.views.Playlist({collection: playlist});
    }
  });

  new YTPL.Router();
  Backbone.history.start();

})(jQuery);