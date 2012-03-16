(function($, undefined) {
  window.YTPL = {models: {}, collections: {}, views: {}};

  _(YTPL.models).extend({
    Video: Backbone.Model.extend({
    })
  });

  _(YTPL.collections).extend({
    Results: Backbone.Collection.extend({
      model: YTPL.models.Video
    }),
    Playlist: Backbone.Collection.extend({
      model: YTPL.models.Video,
      url: function() {
        return '/' + this.plName;
      },
      parse: function(response) {
        return response.videos;
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

  YTPL.views.Video = Backbone.View.extend({
    tagName: 'li',
    className: 'cf',
    events: {
      'click .title': 'play',
      'click img': 'play',
      'click .delete': 'delete'
    },
    template:
      '<img src="<%= thumbnail.url %>">' +
      '<a href="#" class="delete">&times;</a>' +
      '<h3 class="title"><%= title %></h3>' +
      '<span class="author"><%= author %></span>',
    render: function() {
      this.$el.html(_.template(this.template, this.model.toJSON()));
      return this;
    },
    play: function() {
      player.pos = this.model.get('pos');
      player.play();
    },
    'delete': function(e) {
      e.preventDefault();
      this.model.destroy({
        success: _.bind(function(model) {
          this.remove();
        }, this)
      });
    }
  });

  YTPL.views.Playlist = Backbone.View.extend({
    el: '#playlist',
    initialize: function() {
      this.collection.on('add', this.addVideo, this);
      this.collection.on('reset', this.addVideos, this);
    },
    addVideos: function(collection) {
      if (this.collection.length > 0) {
        this.$el.empty();
      }
      collection.each(this.addVideo, this);
    },
    addVideo: function(model) {
      if (this.collection.length == 1) {
        this.$el.empty();
      }
      var view = new YTPL.views.Video({
        model: model
      });
      this.$el.append(view.render().el);
    }
  });

  YTPL.views.Player = Backbone.View.extend({
    pos: 0, // Start with first video
    el: '#player',
    initialize: function() {
      this.collection.on('add', this.playFirstAdd, this);
    },
    setIframe: function() {
      this.ytPlayer = new YT.Player('player', {
        height: '270',
        width: '480',
        events: {
          'onReady': _.bind(this.ready, this),
          'onStateChange': _.bind(this.stateChange, this)
        }
      });
    },
    ready: function(e) {
      // Auto play first video
      this.play();
    },
    play: function() {
      var video = this.collection.at(this.pos);
      if (video) {
        this.ytPlayer.loadVideoById(video.get('vid'));
        this.ytPlayer.playVideo();
      }
    },
    playFirstAdd: function() {
      if (this.collection.length == 1) {
        this.play();
      }
    },
    stateChange: function(e) {
      // Next video
      if (e.data == YT.PlayerState.ENDED) {
        this.pos++;
        if (this.pos >= this.collection.length) {
          this.pos = 0;
        }
        this.play();
      }
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
      results.plName = plName;
      new YTPL.views.Search({collection: results});
      playlist.plName = plName;
      new YTPL.views.Playlist({collection: playlist});
      playlist.fetch({success: function() {
        window.player = new YTPL.views.Player({collection: playlist});
        player.setIframe();
      }});
    }
  });

})(jQuery);

function onYouTubePlayerAPIReady() {
  new YTPL.Router();
  Backbone.history.start();
}